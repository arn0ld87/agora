"""Überträgt Report-Metadaten vom Dateisystem nach PostgreSQL (§11, PR 9).

Was übertragen wird
-------------------
Jede ``uploads/reports/<Schlüssel>/meta.json`` — und jede Datei im
Legacy-Flachformat ``uploads/reports/<Schlüssel>.json`` — nach
``agora.reports``. Gelesen wird über den Dateiadapter, damit der Bestand
genauso ausgelegt wird wie zur Laufzeit (Ordner vor Flachformat, fehlende
optionale Felder mit Vorgabewerten).

**Der Ablageschlüssel bleibt der Schlüssel.** Ein Altbestand kann unter
``report_deepseek_<hex>/`` liegen und ``report_<hex>`` eintragen; die Zeile
bekommt den Ordnernamen als Primärschlüssel, damit Outline, Sections und
Evidence-Map daneben weiter gefunden werden. ``report_id``, ``created_at``
und ``completed_at`` werden übernommen, nicht neu gesetzt.

**Reihenfolge: erst Simulationen, dann Reports.** ``agora.reports`` hat einen
Fremdschlüssel auf ``agora.simulations``. Ein Report, dessen Simulation dort
fehlt, wird einzeln als fehlgeschlagen gemeldet; der Lauf geht weiter.

Was NICHT passiert
------------------
**Das Dateisystem wird nicht angefasst.** ``meta.json`` und alle
Report-Inhalte bleiben unverändert liegen — die Inhalte für immer, die
Metadaten als Wahrheit, bis jemand ``AGORA_REPORT_BACKEND=postgres`` setzt,
und danach als Rückweg.

Aufruf::

    uv run python scripts/migrate_reports_to_postgres.py --dry-run
    uv run python scripts/migrate_reports_to_postgres.py
    uv run python scripts/migrate_reports_to_postgres.py --verify
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
from app.contracts.report_record_contract import ReportRecord  # noqa: E402
from app.infrastructure.postgres.repositories.report_repository import (  # noqa: E402
    PostgresReportRepository,
    ReportSimulationMissing,
)
from app.services.file_report_store import FileReportRepository  # noqa: E402

META_FILENAME = 'meta.json'


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


def reports_dir() -> Path:
    """Dasselbe Verzeichnis, das ``ReportManager.REPORTS_DIR`` bildet."""
    return Path(Config.UPLOAD_FOLDER) / 'reports'


def _candidate_keys(root: Path) -> List[str]:
    """Ablageschlüssel mit Metadaten — ausschliesslich lesend.

    Nicht über ``FileReportRepository.list_ids``: das legt ein fehlendes
    Verzeichnis an. Ein Ordner ohne ``meta.json`` (und ohne Flachdatei) ist
    kein Report und wird übergangen.
    """
    keys: dict[str, None] = {}
    for entry in sorted(root.iterdir()):
        if entry.name.startswith('.'):
            continue
        if entry.is_dir() and (entry / META_FILENAME).is_file():
            keys.setdefault(entry.name, None)
        elif entry.is_file() and entry.suffix == '.json':
            keys.setdefault(entry.stem, None)
    return list(keys)


def read_file_reports(
    root: Path,
) -> Tuple[List[Tuple[str, ReportRecord]], List[str]]:
    """``(Schlüssel, Datensatz)`` je lesbarem Report plus Fehlerliste.

    Ein **unlesbares** Manifest bricht nicht ab, sondern landet mit seinem
    Schlüssel in der Fehlerliste — der Rest des Bestands soll trotzdem
    übertragen werden, und der Bericht nennt jede Lücke.
    """
    if not root.is_dir():
        return [], []

    reader = FileReportRepository(str(root))
    records: List[Tuple[str, ReportRecord]] = []
    failures: List[str] = []
    for key in _candidate_keys(root):
        try:
            record = reader.get(key)
        except (ValueError, OSError) as exc:
            failures.append(f'{key}: meta.json unlesbar ({type(exc).__name__})')
            continue
        if record is None:
            # Der Dateiadapter liefert ``None`` für ein leeres, kaputtes oder
            # unvollständiges Manifest — zur Laufzeit richtig, hier eine Lücke.
            failures.append(f'{key}: meta.json leer, unlesbar oder ohne Pflichtfeld')
            continue
        records.append((key, record))
    return records, failures


def migrate(
    root: Path,
    *,
    dry_run: bool = False,
    repository: Optional[PostgresReportRepository] = None,
) -> Summary:
    """Schreibt den Bestand nach ``agora.reports``.

    Idempotent: ein Schlüssel, der schon in der Tabelle steht, wird
    übersprungen und nicht überschrieben.
    """
    records, failures = read_file_reports(root)
    summary = Summary(scanned=len(records) + len(failures), failures=list(failures))

    if dry_run:
        return summary

    target = repository or PostgresReportRepository()
    for key, record in records:
        try:
            if target.add_existing(key, record):
                summary.inserted += 1
            else:
                summary.skipped += 1
        except ReportSimulationMissing:
            summary.failures.append(
                f'{key}: Simulation {record.simulation_id} fehlt in '
                'agora.simulations (erst Simulationen migrieren; sonst siehe '
                'Runbook)'
            )
    return summary


@dataclass
class VerifyResult:
    """Ergebnis von ``verify``: geprüfte Datensätze, abweichende Schlüssel, Details."""

    checked: int = 0
    mismatched: set[str] = field(default_factory=set)
    deviations: List[str] = field(default_factory=list)

    @property
    def verified(self) -> int:
        return self.checked - len(self.mismatched)


def verify(
    root: Path, *, repository: Optional[PostgresReportRepository] = None
) -> VerifyResult:
    """Vergleicht beide Seiten feldweise.

    Verglichen wird ``to_dict()`` gegen ``to_dict()`` unter demselben
    Ablageschlüssel — die Form, die in ``meta.json`` steht. Ein unlesbares
    Manifest zählt als Abweichung.
    """
    records, failures = read_file_reports(root)
    result = VerifyResult(checked=len(records), deviations=list(failures))
    source = repository or PostgresReportRepository()

    for key, file_record in records:
        db_record = source.get(key)
        if db_record is None:
            result.mismatched.add(key)
            result.deviations.append(f'{key}: fehlt in agora.reports')
            continue
        from_file = file_record.to_dict()
        from_db = db_record.to_dict()
        for field_name in sorted(from_file):
            if from_file[field_name] != from_db.get(field_name):
                result.mismatched.add(key)
                result.deviations.append(
                    f'{key}.{field_name}: '
                    f'Datei={from_file[field_name]!r} DB={from_db.get(field_name)!r}'
                )
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument(
        '--reports-dir',
        type=Path,
        default=None,
        help='abweichendes Report-Verzeichnis (Standard: uploads/reports)',
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='nur lesen und zählen')
    mode.add_argument(
        '--verify',
        action='store_true',
        help='beide Seiten feldweise vergleichen, nichts schreiben',
    )
    args = parser.parse_args(argv)

    root = args.reports_dir or reports_dir()

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
