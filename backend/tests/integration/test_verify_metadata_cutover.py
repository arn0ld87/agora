"""``verify_metadata_cutover.py`` gegen eine echte PostgreSQL-Instanz (#1590).

Ein Legacy-Bestand aus allen fünf Domänen wird mit den Einzelskripten
migriert; danach muss die Sammelprüfung jeden Schritt grün melden — und rot,
sobald ein Datensatz abweicht oder das Schema nicht auf dem Head steht.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterator

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from cryptography.fernet import Fernet
from sqlalchemy import text

from app.config import Config
from app.contracts import Project
from app.contracts.report_record_contract import ReportRecord
from app.contracts.simulation_record_contract import SimulationRecord
from app.infrastructure.postgres import session as session_module
from app.infrastructure.postgres.session import Database
from app.services.llm_profile_secrets_store import LlmProfileSecretsStore
from scripts import migrate_llm_profiles_to_postgres as migrate_llm
from scripts import migrate_projects_to_postgres as migrate_projects
from scripts import migrate_reports_to_postgres as migrate_reports
from scripts import migrate_runs_to_postgres as migrate_runs
from scripts import migrate_simulations_to_postgres as migrate_simulations
from scripts import migration_baseline
from scripts import verify_metadata_cutover as cutover

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = BACKEND_DIR / 'migrations'

PROJECT_ID = 'proj_112233445566'
SIM_ID = 'sim_112233445566'
RUN_ID = 'run_112233445566'
REPORT_ID = 'report_112233445566'
PROFILE_ID = 'a1b2c3d4e5f60718293a4b5c6d7e8f90'


def _alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    return config


@pytest.fixture
def database(postgres_database_url: str, monkeypatch) -> Iterator[Database]:
    """Wegwerf-Datenbank auf dem Head, als Prozess-Adapter eingehängt."""
    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    monkeypatch.setenv('AGORA_SECRET_KEY', Fernet.generate_key().decode())
    command.upgrade(_alembic_config(), 'head')
    db = Database(postgres_database_url)
    monkeypatch.setattr(session_module, '_database', db)
    monkeypatch.setattr(Config, 'DATABASE_URL', postgres_database_url)
    try:
        yield db
    finally:
        db.dispose()


@pytest.fixture
def bestand(tmp_path: Path) -> cutover.CutoverOptions:
    """Je ein Datensatz aus allen fünf Domänen im Legacy-Format."""
    uploads = tmp_path / 'uploads'
    project = Project(
        project_id=PROJECT_ID,
        name='Projekt',
        created_at='2026-09-01T10:00:00',
        updated_at='2026-09-01T10:00:00',
    )
    (uploads / 'projects' / PROJECT_ID).mkdir(parents=True)
    (uploads / 'projects' / PROJECT_ID / 'project.json').write_text(
        json.dumps(project.to_dict()), encoding='utf-8'
    )
    simulation = SimulationRecord(
        simulation_id=SIM_ID,
        project_id=PROJECT_ID,
        graph_id='graph_1',
        status='completed',
        created_at='2026-09-01T11:00:00',
        updated_at='2026-09-01T12:00:00',
    )
    (uploads / 'simulations' / SIM_ID).mkdir(parents=True)
    (uploads / 'simulations' / SIM_ID / 'state.json').write_text(
        json.dumps(simulation.to_dict()), encoding='utf-8'
    )
    (uploads / 'run_registry').mkdir(parents=True)
    (uploads / 'run_registry' / f'{RUN_ID}.json').write_text(
        json.dumps(
            {
                'run_id': RUN_ID,
                'run_type': 'simulation_run',
                'entity_id': SIM_ID,
                'status': 'completed',
                'started_at': '2026-09-01T11:30:00',
                'updated_at': '2026-09-01T12:00:00',
                'linked_ids': {'simulation_id': SIM_ID, 'project_id': PROJECT_ID},
                'events': [],
            }
        ),
        encoding='utf-8',
    )
    report = ReportRecord(
        report_id=REPORT_ID,
        simulation_id=SIM_ID,
        graph_id='graph_1',
        simulation_requirement='Frage',
        status='completed',
        created_at='2026-09-01T13:00:00',
    )
    (uploads / 'reports' / REPORT_ID).mkdir(parents=True)
    (uploads / 'reports' / REPORT_ID / 'meta.json').write_text(
        json.dumps(report.to_dict()), encoding='utf-8'
    )

    instance = tmp_path / 'instance'
    instance.mkdir()
    db_path = instance / 'llm_profiles.db'
    conn = sqlite3.connect(db_path)
    conn.execute(
        'CREATE TABLE llm_profiles (id TEXT PRIMARY KEY, name TEXT, '
        'provider TEXT, base_url TEXT, model_name TEXT, api_key TEXT, '
        'is_default INTEGER, created_at TEXT, updated_at TEXT)'
    )
    conn.execute(
        'INSERT INTO llm_profiles VALUES (?,?,?,?,?,?,?,?,?)',
        (
            PROFILE_ID, 'Profil', 'ollama', 'http://host:11434', 'modell', 'KEY', 1,
            '2026-03-01T08:00:00+00:00', '2026-03-02T09:00:00+00:00',
        ),
    )
    conn.commit()
    conn.close()

    return cutover.CutoverOptions(
        uploads_dir=uploads,
        simulations_dir=uploads / 'simulations',
        llm_profiles_db=db_path,
        secrets_dir=tmp_path / 'data',
    )


def _migrate_everything(options: cutover.CutoverOptions) -> None:
    uploads = options.uploads_dir
    secrets = LlmProfileSecretsStore(data_dir=options.secrets_dir)
    assert migrate_llm.migrate(options.llm_profiles_db, secrets) == 1
    assert migrate_projects.migrate(uploads / 'projects')['uebertragen'] == 1
    assert migrate_simulations.migrate(options.simulations_dir).failed == 0
    assert migrate_runs.migrate(uploads / 'run_registry').failed == 0
    assert migrate_reports.migrate(uploads / 'reports').failed == 0


def _manifest(options: cutover.CutoverOptions, path: Path) -> Path:
    manifest = migration_baseline.build_manifest(
        BACKEND_DIR.parent,
        options.uploads_dir,
        options.llm_profiles_db.parent,
        with_graph=False,
    ).to_dict()
    # Ohne Neo4j sind die Graph-Klassen ungeprüft; hier geht es um die
    # Metadaten, also bleiben sie aus dem Vergleich.
    manifest['classes'] = [c for c in manifest['classes'] if not c['name'].startswith('graph_')]
    path.write_text(json.dumps(manifest), encoding='utf-8')
    return path


def _postgres_everywhere(monkeypatch) -> None:
    for name in ('PROJECT_BACKEND', 'SIMULATION_BACKEND', 'RUN_BACKEND', 'REPORT_BACKEND'):
        monkeypatch.setattr(Config, name, 'postgres')
    monkeypatch.setattr(Config, 'LLM_PROFILE_BACKEND', 'postgres')


def test_all_steps_green_after_a_full_migration(database, bestand, tmp_path, monkeypatch):
    vorher = _manifest(bestand, tmp_path / 'vorher.json')
    _migrate_everything(bestand)
    bestand.baseline = [vorher, _manifest(bestand, tmp_path / 'nachher.json')]
    _postgres_everywhere(monkeypatch)

    results = cutover.run_checks(bestand)

    assert {r.name: r.status for r in results} == {
        name: cutover.OK
        for name in (
            'flags', 'alembic_head', 'llm_profiles', 'projects',
            'simulations', 'runs', 'reports', 'baseline',
        )
    }
    assert {r.name: (r.verified, r.checked) for r in results if r.name in (
        'llm_profiles', 'projects', 'simulations', 'runs', 'reports'
    )} == {name: (1, 1) for name in ('llm_profiles', 'projects', 'simulations', 'runs', 'reports')}
    assert cutover.exit_code(results) == 0


def test_a_changed_run_turns_only_the_runs_step_red(database, bestand, monkeypatch):
    _migrate_everything(bestand)
    with database.session() as session:
        session.execute(
            text(
                "UPDATE agora.runs SET payload = jsonb_set(payload, '{status}', "
                f"'\"failed\"') WHERE id = '{RUN_ID}'"
            )
        )

    results = {r.name: r for r in cutover.run_checks(bestand)}

    assert results['runs'].status == cutover.FAILED
    assert any(f'{RUN_ID}.status' in line for line in results['runs'].details)
    assert results['reports'].status == cutover.OK
    assert results['baseline'].status == cutover.UNCHECKED


def test_missing_migration_and_schema_drift_are_reported(database, bestand, postgres_database_url):
    """Ohne Datenmigration fehlen die Datensätze; ein Schritt unter dem Head
    ist Drift. Beides muss rot sein, nicht still grün."""
    results = {r.name: r for r in cutover.run_checks(bestand)}
    assert results['projects'].status == cutover.FAILED
    assert results['reports'].status == cutover.FAILED

    command.downgrade(_alembic_config(), '3f9b2d7e6a41')
    results = {r.name: r for r in cutover.run_checks(bestand)}

    assert results['alembic_head'].status == cutover.FAILED
    assert results['reports'].status == cutover.FAILED
    assert cutover.exit_code(list(results.values())) == 1
    assert postgres_database_url not in cutover.render(list(results.values()))
