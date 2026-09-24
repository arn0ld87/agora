"""Überträgt Run-Manifeste vom Dateisystem nach PostgreSQL (§11, PR 8).

Was übertragen wird
-------------------
Jede ``uploads/run_registry/<run_id>.json`` nach ``agora.runs``. Gelesen wird
über den Dateiadapter, damit der Bestand genauso ausgelegt wird wie zur
Laufzeit (nachsichtiger Vertrag, fehlende Felder bleiben fehlend); das
Manifest geht unverändert ins ``payload``.

**Kennungen und Zeitstempel bleiben unverändert.** ``run_id``,
``started_at``, ``updated_at`` und ``completed_at`` werden übernommen, nicht
neu gesetzt. Events, Artefakt-Verweise und Lease-Felder im ``metadata``
gehen mit.

**Reihenfolge: erst Simulationen, dann Runs.** ``agora.runs`` hat einen
Fremdschlüssel auf ``agora.simulations`` (aus ``linked_ids.simulation_id``).
Ein Run, dessen Simulation dort fehlt, wird einzeln als fehlgeschlagen
gemeldet; der Lauf geht weiter.

Was NICHT passiert
------------------
**Das Dateisystem wird nicht angefasst.** Die Manifeste bleiben unverändert
liegen — als Wahrheit, bis jemand ``AGORA_RUN_BACKEND=postgres`` setzt, und
danach als Rückweg. Temp-Dateien atomarer Schreibvorgänge (``.tmp-json-*``)
werden übergangen.

Aufruf::

    uv run python scripts/migrate_runs_to_postgres.py --dry-run
    uv run python scripts/migrate_runs_to_postgres.py
    uv run python scripts/migrate_runs_to_postgres.py --verify
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
from app.contracts.run_record_contract import RunRecord  # noqa: E402
from app.infrastructure.postgres.repositories.run_repository import (  # noqa: E402
    PostgresRunRepository,
    RunSimulationMissing,
)
from app.services.file_run_store import FileRunRepository  # noqa: E402


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


def registry_dir() -> Path:
    """Dasselbe Verzeichnis, das ``RunRegistry.REGISTRY_DIR`` bildet."""
    return Path(Config.UPLOAD_FOLDER) / 'run_registry'


def read_file_runs(root: Path) -> Tuple[List[RunRecord], List[str]]:
    """Liest den Bestand, ausschliesslich lesend.

    Nicht über ``FileRunRepository.list_all``: das legt ein fehlendes
    Verzeichnis an und verschweigt unlesbare Manifeste. Hier landet jedes
    unlesbare Manifest mit seiner Kennung in der Fehlerliste — der Rest des
    Bestands soll trotzdem übertragen werden, und der Bericht nennt jede
    Lücke.
    """
    if not root.is_dir():
        return [], []

    reader = FileRunRepository(str(root))
    records: List[RunRecord] = []
    failures: List[str] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_file() or entry.name.startswith('.'):
            continue
        if entry.suffix != '.json':
            continue
        run_id = entry.stem
        try:
            record = reader.get(run_id)
        except (ValueError, OSError) as exc:
            failures.append(f'{run_id}: Manifest unlesbar ({type(exc).__name__})')
            continue
        if record is None:
            # Der Dateiadapter liefert ``None`` auch für ein leeres oder
            # kaputtes Manifest — zur Laufzeit richtig, hier eine Lücke.
            failures.append(f'{run_id}: Manifest leer oder unlesbar')
            continue
        if record.run_id != run_id:
            # ``get`` findet einen Run über den Dateinamen; landete er in
            # PostgreSQL unter einer anderen Kennung, fände ihn niemand wieder.
            failures.append(
                f'{run_id}: Manifest trägt abweichende run_id {record.run_id!r}'
            )
            continue
        records.append(record)
    return records, failures


def migrate(
    root: Path,
    *,
    dry_run: bool = False,
    repository: Optional[PostgresRunRepository] = None,
) -> Summary:
    """Schreibt den Bestand nach ``agora.runs``.

    Idempotent: eine Kennung, die schon in der Tabelle steht, wird
    übersprungen und nicht überschrieben.
    """
    records, failures = read_file_runs(root)
    summary = Summary(scanned=len(records) + len(failures), failures=list(failures))

    if dry_run:
        return summary

    target = repository or PostgresRunRepository()
    for record in records:
        try:
            if target.add_existing(record):
                summary.inserted += 1
            else:
                summary.skipped += 1
        except RunSimulationMissing:
            simulation_id = record.linked_ids.get('simulation_id')
            summary.failures.append(
                f'{record.run_id}: Simulation {simulation_id} fehlt in '
                'agora.simulations (erst Simulationen migrieren; sonst siehe '
                'Runbook)'
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
    root: Path, *, repository: Optional[PostgresRunRepository] = None
) -> VerifyResult:
    """Vergleicht beide Seiten feldweise.

    Verglichen wird ``to_manifest()`` gegen ``to_manifest()`` — die Form, die
    in der Datei steht. Ein Feld, das nur auf einer Seite existiert, zählt
    als Abweichung; ein unlesbares Manifest ebenfalls.
    """
    records, failures = read_file_runs(root)
    result = VerifyResult(checked=len(records), deviations=list(failures))
    source = repository or PostgresRunRepository()

    for file_record in records:
        run_id = file_record.run_id
        db_record = source.get(run_id)
        if db_record is None:
            result.mismatched.add(run_id)
            result.deviations.append(f'{run_id}: fehlt in agora.runs')
            continue
        from_file = file_record.to_manifest()
        from_db = db_record.to_manifest()
        for key in sorted(set(from_file) | set(from_db)):
            if key not in from_file or key not in from_db or from_file[key] != from_db[key]:
                result.mismatched.add(run_id)
                result.deviations.append(
                    f'{run_id}.{key}: '
                    f'Datei={from_file.get(key, "<fehlt>")!r} '
                    f'DB={from_db.get(key, "<fehlt>")!r}'
                )
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument(
        '--registry-dir',
        type=Path,
        default=None,
        help='abweichendes Registry-Verzeichnis (Standard: uploads/run_registry)',
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='nur lesen und zählen')
    mode.add_argument(
        '--verify',
        action='store_true',
        help='beide Seiten feldweise vergleichen, nichts schreiben',
    )
    args = parser.parse_args(argv)

    root = args.registry_dir or registry_dir()

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
