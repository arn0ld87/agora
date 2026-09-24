"""Überträgt Simulationsmetadaten vom Dateisystem nach PostgreSQL (§11, PR 7).

Was übertragen wird
-------------------
Der Inhalt jeder ``uploads/simulations/<simulation_id>/state.json`` nach
``agora.simulations``. Gelesen wird über den Dateiadapter, damit der Bestand
genauso ausgelegt wird wie zur Laufzeit (Altbestand mit ``null``-Feldern,
fehlende Zeitstempel); die Aufteilung auf Kernspalten und ``payload`` macht
der PostgreSQL-Adapter.

**Kennungen und Zeitstempel bleiben unverändert.** ``simulation_id`` ist der
Verzeichnisname der Laufzeit-Artefakte; ``created_at``/``updated_at`` werden
übernommen, nicht neu gesetzt.

**Reihenfolge: erst Projekte, dann Simulationen.** ``agora.simulations`` hat
einen Fremdschlüssel auf ``agora.projects``. Eine Simulation, deren Projekt
dort fehlt — noch nicht migriert oder längst gelöscht —, wird einzeln als
fehlgeschlagen gemeldet; der Lauf geht weiter.

Was NICHT passiert
------------------
**Das Dateisystem wird nicht angefasst.** ``state.json`` und die Artefakte
daneben bleiben unverändert liegen — als Wahrheit, bis jemand
``AGORA_SIMULATION_BACKEND=postgres`` setzt, und danach als Rückweg.

Aufruf::

    uv run python scripts/migrate_simulations_to_postgres.py --dry-run
    uv run python scripts/migrate_simulations_to_postgres.py
    uv run python scripts/migrate_simulations_to_postgres.py --verify
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import Config  # noqa: E402
from app.contracts.simulation_record_contract import SimulationRecord  # noqa: E402
from app.infrastructure.postgres.repositories.simulation_repository import (  # noqa: E402
    PostgresSimulationRepository,
    SimulationProjectMissing,
)
from app.services.file_simulation_store import FileSimulationRepository  # noqa: E402

STATE_FILENAME = 'state.json'


@dataclass
class Summary:
    """Zusammenfassung nach §33: jede Zahl einzeln, Fehler mit Kennung."""

    scanned: int = 0
    inserted: int = 0
    skipped: int = 0
    failures: List[str] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return len(self.failures)


def simulations_dir() -> Path:
    """Dasselbe Verzeichnis, das ``Config.OASIS_SIMULATION_DATA_DIR`` bildet."""
    return Path(Config.OASIS_SIMULATION_DATA_DIR)


def read_file_simulations(
    root: Path,
) -> Tuple[List[SimulationRecord], List[str]]:
    """Liest den Bestand, ausschliesslich lesend.

    Ein Verzeichnis ohne ``state.json`` ist keine Simulation und wird
    übergangen. Eine **unlesbare** ``state.json`` bricht nicht ab, sondern
    landet mit ihrer Kennung in der Fehlerliste — der Rest des Bestands soll
    trotzdem übertragen werden, und der Bericht nennt jede Lücke.
    """
    if not root.exists():
        return [], []

    reader = FileSimulationRepository(simulations_dir=str(root))
    records: List[SimulationRecord] = []
    failures: List[str] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith('.'):
            continue
        if not (entry / STATE_FILENAME).exists():
            continue
        try:
            record = reader.get(entry.name)
        except (ValueError, OSError) as exc:
            failures.append(f'{entry.name}: state.json unlesbar ({type(exc).__name__})')
            continue
        if record is None:
            # Der Dateiadapter liefert ``None`` auch für eine leere oder
            # kaputte ``state.json`` — zur Laufzeit richtig, hier eine Lücke,
            # die im Bericht stehen muss.
            failures.append(f'{entry.name}: state.json leer oder unlesbar')
            continue
        records.append(record)
    return records, failures


def migrate(
    root: Path,
    *,
    dry_run: bool = False,
    repository: Optional[PostgresSimulationRepository] = None,
) -> Summary:
    """Schreibt den Bestand nach ``agora.simulations``.

    Idempotent: eine Kennung, die schon in der Tabelle steht, wird
    übersprungen und nicht überschrieben.
    """
    records, failures = read_file_simulations(root)
    summary = Summary(scanned=len(records) + len(failures), failures=list(failures))

    if dry_run:
        return summary

    target = repository or PostgresSimulationRepository()
    for record in records:
        try:
            if target.add_existing(record):
                summary.inserted += 1
            else:
                summary.skipped += 1
        except SimulationProjectMissing:
            summary.failures.append(
                f'{record.simulation_id}: Projekt {record.project_id} fehlt in '
                'agora.projects (erst Projekte migrieren; bei gelöschtem Projekt '
                'siehe Runbook)'
            )
    return summary


@dataclass
class VerifyResult:
    """Ergebnis von ``verify``: geprüfte Datensätze, abweichende Kennungen, Details."""

    checked: int = 0
    mismatched: set[str] = field(default_factory=set)
    deviations: List[str] = field(default_factory=list)

    @property
    def verified(self) -> int:
        return self.checked - len(self.mismatched)


def verify(
    root: Path, *, repository: Optional[PostgresSimulationRepository] = None
) -> VerifyResult:
    """Vergleicht beide Seiten feldweise.

    Verglichen wird ``to_dict()`` gegen ``to_dict()`` — die Form, die in
    ``state.json`` steht. Keine Abweichung heisst: jedes Feld jeder
    Simulation stimmt. Eine unlesbare ``state.json`` zählt als Abweichung.
    """
    records, failures = read_file_simulations(root)
    result = VerifyResult(checked=len(records), deviations=list(failures))
    source = repository or PostgresSimulationRepository()

    for file_record in records:
        sim_id = file_record.simulation_id
        db_record = source.get(sim_id)
        if db_record is None:
            result.mismatched.add(sim_id)
            result.deviations.append(f'{sim_id}: fehlt in agora.simulations')
            continue
        from_file = file_record.to_dict()
        from_db = db_record.to_dict()
        for key in sorted(from_file):
            if from_file[key] != from_db.get(key):
                result.mismatched.add(sim_id)
                result.deviations.append(
                    f'{sim_id}.{key}: '
                    f'Datei={from_file[key]!r} DB={from_db.get(key)!r}'
                )
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument(
        '--simulations-dir',
        type=Path,
        default=None,
        help='abweichendes Simulationsverzeichnis (Standard: uploads/simulations)',
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='nur lesen und zählen')
    mode.add_argument(
        '--verify',
        action='store_true',
        help='beide Seiten feldweise vergleichen, nichts schreiben',
    )
    args = parser.parse_args(argv)

    root = args.simulations_dir or simulations_dir()

    if args.verify:
        result = verify(root)
        for line in result.deviations:
            sys.stdout.write(f'ABWEICHUNG: {line}\n')
        sys.stdout.write(f'Verified:  {result.verified}/{result.checked}\n')
        return 0 if not result.deviations else 1

    summary = migrate(root, dry_run=args.dry_run)
    prefix = 'DRY-RUN\n' if args.dry_run else ''
    sys.stdout.write(
        f'{prefix}'
        f'Scanned:   {summary.scanned}\n'
        f'Inserted:  {summary.inserted}\n'
        f'Skipped:   {summary.skipped}\n'
        f'Failed:    {summary.failed}\n'
    )
    for line in summary.failures:
        sys.stdout.write(f'FEHLER: {line}\n')
    return 0 if summary.failed == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
