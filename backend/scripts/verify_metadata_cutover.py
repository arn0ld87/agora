"""Sammelprüfung vor und nach dem Metadaten-Cutover auf PostgreSQL (#1590).

Warum das existiert
-------------------
Jede Domäne hat ihr eigenes ``migrate_*_to_postgres.py --verify``, dazu kommen
das Alembic-Start-Gate (#1582) und die Migrations-Baseline (§6). Einzeln
gefahren übersieht man leicht einen Schritt. Dieses Skript fährt alle in der
Cutover-Reihenfolge und gibt **Exit 0 nur, wenn jeder Schritt grün ist**.

Die Schritte
------------
1. ``flags`` — Die Schalter sind untereinander konsistent. Es gelten dieselben
   Regeln wie in ``Config.validate()``: Fremdschlüssel-Reihenfolge LLM-Profile
   → Projekte → Simulationen → Runs → Reports, dazu ``DATABASE_URL``.
2. ``alembic_head`` — Die Datenbank steht auf dem Alembic-Head aus
   ``migrations/``. Das prüft dieselbe Funktion, die den App-Start abbricht.
3. ``llm_profiles``, ``projects``, ``simulations``, ``runs``, ``reports`` —
   Das ``verify`` des jeweiligen Migrationsskripts vergleicht beide Seiten
   feldweise.
4. ``baseline`` — ``migration_baseline.py --compare`` zweier Manifeste
   (vor und nach der Migration). Ohne ``--baseline VORHER NACHHER`` bleibt der
   Schritt ungeprüft.

Ergebnis
--------
Ein Schritt ist ``OK``, ``FEHLER`` oder ``UNGEPRÜFT``. Ein ungeprüfter Schritt
ist kein Erfolg: Exit 0 nur, wenn alle Schritte ``OK`` sind, Exit 1 bei
mindestens einem Fehler, sonst Exit 2. Die Zusammenfassung folgt Plan §33.
``Inserted`` steht immer auf 0, weil das Skript nichts schreibt.

Das Skript liest ausschliesslich. Es schreibt weder in die Datenbank noch ins
Dateisystem. In der Ausgabe erscheinen nie eine Verbindungszeichenkette oder
ein Geheimnis, von einer Ausnahme nur ihr Typ.

Aufruf::

    uv run python scripts/verify_metadata_cutover.py
    uv run python scripts/verify_metadata_cutover.py --baseline /tmp/vorher.json /tmp/nachher.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence

from pydantic import BaseModel, Field

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import (  # noqa: E402
    Config,
    validate_database_settings,
    validate_llm_profile_backend,
    validate_project_backend,
    validate_report_backend,
    validate_run_backend,
    validate_simulation_backend,
)

OK = 'OK'
FAILED = 'FEHLER'
UNCHECKED = 'UNGEPRÜFT'

#: Ausgabe-Beschränkung je Schritt: der Bericht soll lesbar bleiben, die
#: Einzelskripte liefern auf Wunsch alle Zeilen.
MAX_DETAILS = 20


class StepResult(BaseModel):
    """Ergebnis eines Prüfschritts.

    Pydantic statt ``dataclass`` nach der Projektregel (AGENTS.md; derselbe
    Befund wie im Codex-Review auf #1607).
    """

    name: str
    status: str
    checked: int = 0
    verified: int = 0
    details: List[str] = Field(default_factory=list)


class CutoverOptions(BaseModel):
    """Pfade und Eingaben. Die Vorgaben sind die Laufzeitpfade."""

    uploads_dir: Path = Field(default_factory=lambda: Path(Config.UPLOAD_FOLDER))
    simulations_dir: Path = Field(
        default_factory=lambda: Path(Config.OASIS_SIMULATION_DATA_DIR)
    )
    llm_profiles_db: Path = BACKEND_DIR / 'instance' / 'llm_profiles.db'
    secrets_dir: Optional[Path] = None
    baseline: Optional[List[Path]] = None


# -- Schritt 1: Schalter -----------------------------------------------------


def check_flags(config: Any = Config) -> StepResult:
    """Dieselben Regeln wie ``Config.validate()``, auf die Metadaten-Schalter
    beschränkt. Die Fremdschlüssel-Reihenfolge steckt in den ``validate_*``-
    Funktionen: Simulationen verlangen Projekte, Runs und Reports verlangen
    Simulationen."""
    url = getattr(config, 'DATABASE_URL', '') or ''
    simulation = getattr(config, 'SIMULATION_BACKEND', 'file')
    errors: List[str] = []
    errors += validate_database_settings(getattr(config, 'METADATA_BACKEND', 'legacy'), url)
    errors += validate_llm_profile_backend(getattr(config, 'LLM_PROFILE_BACKEND', 'sqlite'))
    errors += validate_project_backend(getattr(config, 'PROJECT_BACKEND', 'file'), url)
    errors += validate_simulation_backend(
        simulation, url, getattr(config, 'PROJECT_BACKEND', 'file')
    )
    errors += validate_run_backend(getattr(config, 'RUN_BACKEND', 'file'), url, simulation)
    errors += validate_report_backend(
        getattr(config, 'REPORT_BACKEND', 'file'), url, simulation
    )
    if not url.strip():
        errors.append('DATABASE_URL is not set — nothing to verify against')
    status = OK if not errors else FAILED
    return StepResult(name='flags', status=status, checked=1, verified=int(not errors), details=errors)


# -- Schritt 2: Alembic-Head -------------------------------------------------


def check_alembic_head(database_url: Optional[str] = None) -> StepResult:
    from app.infrastructure.postgres.schema_gate import (
        SchemaDriftError,
        verify_schema_at_head,
    )

    url = (database_url if database_url is not None else Config.DATABASE_URL or '').strip()
    if not url:
        return StepResult(name='alembic_head', status=UNCHECKED, details=['DATABASE_URL is not set'])
    try:
        verify_schema_at_head(url)
    except SchemaDriftError as exc:
        # Die Meldung nennt nur Revisionen, nie die URL.
        return StepResult(name='alembic_head', status=FAILED, checked=1, details=[str(exc)])
    return StepResult(name='alembic_head', status=OK, checked=1, verified=1)


# -- Schritt 3: Datenvergleich je Domäne --------------------------------------


def _from_verify_result(name: str, result: Any) -> StepResult:
    """``VerifyResult`` (Simulationen, Runs, Reports) → ``StepResult``."""
    status = OK if not result.deviations else FAILED
    return StepResult(
        name=name,
        status=status,
        checked=result.checked,
        verified=result.verified,
        details=list(result.deviations),
    )


def _from_findings(name: str, checked: int, findings: List[str]) -> StepResult:
    """Abweichungsliste (Projekte, LLM-Profile) → ``StepResult``.

    Diese Skripte liefern keine Zahl geprüfter Datensätze mit; ``checked``
    kommt vom Aufrufer. Als verifiziert gilt, was ohne Befund blieb. Ein
    Befund wird seiner Kennung zugeordnet (Text vor dem ersten ``.`` oder
    ``:``); der Status ist bei jedem Befund ``FEHLER``.
    """
    if not findings:
        return StepResult(name=name, status=OK, checked=checked, verified=checked)
    affected = {line.split('.', 1)[0].split(':', 1)[0] for line in findings}
    verified = max(checked - len(affected), 0)
    return StepResult(name=name, status=FAILED, checked=checked, verified=verified, details=findings)


#: Abfrage je Tabelle, deren Zeilen gegen die Quelle gezählt werden. Feste
#: Texte statt eines eingesetzten Tabellennamens.
TARGET_ID_QUERIES: dict[str, str] = {
    'projects': 'SELECT id FROM agora.projects',
    'simulations': 'SELECT id FROM agora.simulations',
    'runs': 'SELECT id FROM agora.runs',
    'reports': 'SELECT id FROM agora.reports',
}


def target_ids(table: str) -> set[str]:
    """Alle Primärschlüssel einer Zieltabelle, auch unlesbare Zeilen.

    Bewusst nicht über die Repositories: deren Listen überspringen kaputte
    Zeilen oder haben ein Limit, und genau solche Zeilen soll die Prüfung
    finden (Codex-Review auf #1608).
    """
    from sqlalchemy import text

    from app.infrastructure.postgres.session import get_database

    query = TARGET_ID_QUERIES.get(table)
    if query is None:
        raise ValueError(f'unbekannte Tabelle: {table}')
    with get_database().session() as session:
        return {str(key) for key in session.scalars(text(query))}


def _missing_source(name: str, path: Path) -> StepResult:
    """Eine fehlende Quelle ist kein leerer, geprüfter Bestand.

    Ein vertippter ``--uploads-dir`` oder ein nicht eingehängtes Volume sähe
    sonst aus wie ``OK 0/0`` (Codex-Review auf #1608).
    """
    return StepResult(
        name=name,
        status=UNCHECKED,
        details=[f'Quelle fehlt: {path} — Pfad prüfen oder Volume einhängen'],
    )


def _key_of(line: str) -> str:
    """Kennung aus einer Fehlerzeile der Migrationsskripte (``<id>: …``)."""
    return line.split(':', 1)[0].strip()


def _with_target_only(result: StepResult, table: str, source_ids: set[str]) -> StepResult:
    """Zeilen, die nur in PostgreSQL stehen, machen den Schritt rot.

    Das ``--verify`` der Migrationsskripte läuft nur über die Quelle. Reste
    eines früheren Versuchs wären danach nach dem Umschalten sichtbar, ohne
    dass die Prüfung sie gemeldet hätte (Codex-Review auf #1608).
    """
    extra = sorted(target_ids(table) - source_ids)
    if not extra:
        return result
    details = list(result.details) + [
        f'{key}: nur in agora.{table}, nicht in der Quelle' for key in extra
    ]
    return result.model_copy(update={'status': FAILED, 'details': details})


def check_llm_profiles(options: CutoverOptions) -> StepResult:
    from scripts import migrate_llm_profiles_to_postgres as skript
    from app.services.llm_profile_secrets_store import LlmProfileSecretsStore

    if not options.llm_profiles_db.is_file():
        return _missing_source('llm_profiles', options.llm_profiles_db)
    # ``verify`` vergleicht hier schon die Anzahl beider Seiten; Zeilen nur in
    # PostgreSQL fallen damit auf.
    checked = len(skript.read_sqlite_profiles(options.llm_profiles_db))
    secrets = LlmProfileSecretsStore(data_dir=options.secrets_dir)
    return _from_findings(
        'llm_profiles', checked, skript.verify(options.llm_profiles_db, secrets)
    )


def check_projects(options: CutoverOptions) -> StepResult:
    from scripts import migrate_projects_to_postgres as skript

    root = options.uploads_dir / 'projects'
    if not root.is_dir():
        return _missing_source('projects', root)
    projects = skript.read_file_projects(root)
    result = _from_findings('projects', len(projects), skript.verify(root))
    return _with_target_only(result, 'projects', {p.project_id for p in projects})


def check_simulations(options: CutoverOptions) -> StepResult:
    from scripts import migrate_simulations_to_postgres as skript

    root = options.simulations_dir
    if not root.is_dir():
        return _missing_source('simulations', root)
    records, failures = skript.read_file_simulations(root)
    result = _from_verify_result('simulations', skript.verify(root))
    source = {r.simulation_id for r in records} | {_key_of(f) for f in failures}
    return _with_target_only(result, 'simulations', source)


def check_runs(options: CutoverOptions) -> StepResult:
    from scripts import migrate_runs_to_postgres as skript

    root = options.uploads_dir / 'run_registry'
    if not root.is_dir():
        return _missing_source('runs', root)
    records, failures = skript.read_file_runs(root)
    result = _from_verify_result('runs', skript.verify(root))
    source = {r.run_id for r in records} | {_key_of(f) for f in failures}
    return _with_target_only(result, 'runs', source)


def check_reports(options: CutoverOptions) -> StepResult:
    from scripts import migrate_reports_to_postgres as skript

    root = options.uploads_dir / 'reports'
    if not root.is_dir():
        return _missing_source('reports', root)
    records, failures = skript.read_file_reports(root)
    result = _from_verify_result('reports', skript.verify(root))
    source = {key for key, _ in records} | {_key_of(f) for f in failures}
    return _with_target_only(result, 'reports', source)


# -- Schritt 4: Baseline -----------------------------------------------------


def check_baseline(paths: Optional[Sequence[Path]]) -> StepResult:
    from scripts import migration_baseline

    if not paths:
        return StepResult(
            name='baseline',
            status=UNCHECKED,
            details=['--baseline VORHER NACHHER fehlt (scripts/migration_baseline.py)'],
        )
    before, after = (json.loads(Path(p).read_text(encoding='utf-8')) for p in paths)
    findings, unchecked = migration_baseline.compare(before, after)
    if findings:
        return StepResult(name='baseline', status=FAILED, checked=1, details=findings + unchecked)
    if unchecked:
        return StepResult(name='baseline', status=UNCHECKED, checked=1, details=unchecked)
    return StepResult(name='baseline', status=OK, checked=1, verified=1)


# -- Ablauf ------------------------------------------------------------------


def _guarded(name: str, step: Callable[[], StepResult]) -> StepResult:
    """Ein Schritt, der wirft, ist ein Fehler dieses Schritts — nicht des
    ganzen Laufs. Ausgegeben wird nur der Typ: eine Treiber-Meldung kann die
    Verbindungszeichenkette enthalten."""
    try:
        return step()
    except Exception as exc:  # noqa: BLE001 — jeder Fehler wird zum Befund
        return StepResult(name=name, status=FAILED, details=[f'Schritt abgebrochen: {type(exc).__name__}'])


def run_checks(options: CutoverOptions, config: Any = Config) -> List[StepResult]:
    """Alle Schritte in Cutover-Reihenfolge.

    Sind die Schalter inkonsistent oder fehlt ``DATABASE_URL``, laufen die
    Datenbankschritte trotzdem — sie scheitern dann einzeln und sagen, woran.
    """
    steps: List[tuple[str, Callable[[], StepResult]]] = [
        ('flags', lambda: check_flags(config)),
        ('alembic_head', lambda: check_alembic_head(getattr(config, 'DATABASE_URL', ''))),
        ('llm_profiles', lambda: check_llm_profiles(options)),
        ('projects', lambda: check_projects(options)),
        ('simulations', lambda: check_simulations(options)),
        ('runs', lambda: check_runs(options)),
        ('reports', lambda: check_reports(options)),
        ('baseline', lambda: check_baseline(options.baseline)),
    ]
    return [_guarded(name, step) for name, step in steps]


def exit_code(results: Sequence[StepResult]) -> int:
    if any(r.status == FAILED for r in results):
        return 1
    if any(r.status == UNCHECKED for r in results):
        return 2
    return 0


def render(results: Sequence[StepResult]) -> str:
    lines: List[str] = []
    for result in results:
        lines.append(
            f'[{result.status}] {result.name}: Verified {result.verified}/{result.checked}'
        )
        for detail in result.details[:MAX_DETAILS]:
            lines.append(f'    - {detail}')
        if len(result.details) > MAX_DETAILS:
            lines.append(f'    … {len(result.details) - MAX_DETAILS} weitere')
    passed = sum(1 for r in results if r.status == OK)
    failed = sum(1 for r in results if r.status == FAILED)
    skipped = sum(1 for r in results if r.status == UNCHECKED)
    lines += [
        '',
        f'Scanned:   {len(results)}',
        'Inserted:  0',
        f'Skipped:   {skipped}',
        f'Failed:    {failed}',
        f'Verified:  {passed}/{len(results)}',
    ]
    return '\n'.join(lines) + '\n'


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--uploads-dir', type=Path, default=None, help='Standard: UPLOAD_FOLDER')
    parser.add_argument(
        '--simulations-dir', type=Path, default=None, help='Standard: uploads/simulations'
    )
    parser.add_argument(
        '--llm-profiles-db', type=Path, default=None, help='Standard: instance/llm_profiles.db'
    )
    parser.add_argument(
        '--secrets-dir', type=Path, default=None, help='Verzeichnis des Profil-Secret-Stores'
    )
    parser.add_argument(
        '--baseline',
        nargs=2,
        type=Path,
        metavar=('VORHER', 'NACHHER'),
        help='zwei Manifeste aus scripts/migration_baseline.py',
    )
    args = parser.parse_args(argv)

    options = CutoverOptions()
    if args.uploads_dir is not None:
        options.uploads_dir = args.uploads_dir
    if args.simulations_dir is not None:
        options.simulations_dir = args.simulations_dir
    elif args.uploads_dir is not None:
        options.simulations_dir = args.uploads_dir / 'simulations'
    if args.llm_profiles_db is not None:
        options.llm_profiles_db = args.llm_profiles_db
    options.secrets_dir = args.secrets_dir
    options.baseline = args.baseline

    results = run_checks(options)
    sys.stdout.write(render(results))
    return exit_code(results)


if __name__ == '__main__':
    raise SystemExit(main())
