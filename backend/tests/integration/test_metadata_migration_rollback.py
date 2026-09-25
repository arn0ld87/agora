"""Gesamt-Migrations- und Rollback-Gate für den Metadaten-Cutover (#1589, Plan §36).

Der Ablauf, den ein Betreiber fährt, einmal vollständig gegen eine echte
PostgreSQL-Instanz:

1. Legacy-Bestand aus allen fünf Domänen: LLM-Profil (SQLite), Projekt,
   Simulation, Run, Report (Dateien).
2. Alle ``migrate_*_to_postgres.py``, danach jedes ``--verify`` mit Exit 0.
3. App mit allen Schaltern auf ``postgres`` starten. Die Legacy-Metadateien
   sind in dieser Phase versteckt: jede Antwort kommt nachweislich aus der
   Datenbank. Antworten der Profil-, Projekt-, Simulations-, Run- und
   Report-Endpunkte einsammeln.
4. Schalter zurück auf Legacy, Dateien wieder da: die App startet, liefert
   byte-gleiche Antworten, und kein Datensatz fehlt.

Plan §36: "postgres -> legacy backend flag muss ohne Datenverlust starten
können."
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from cryptography.fernet import Fernet

from app.config import Config
from app.contracts import Project
from app.contracts.report_record_contract import ReportRecord
from app.contracts.simulation_record_contract import SimulationRecord
from app.infrastructure.postgres import session as session_module
from app.infrastructure.postgres.session import Database
from app.models.project import ProjectManager
from app.services.report_agent import ReportManager
from app.services.run_registry import RunRegistry
from app.services.simulation_manager import SimulationManager
from app.services.report_prompts import DEFAULT_REPORT_SECTIONS
from scripts import migrate_llm_profiles_to_postgres as migrate_llm
from scripts import migrate_projects_to_postgres as migrate_projects
from scripts import migrate_reports_to_postgres as migrate_reports
from scripts import migrate_runs_to_postgres as migrate_runs
from scripts import migrate_simulations_to_postgres as migrate_simulations

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = BACKEND_DIR / 'migrations'

PROJECT_ID = 'proj_112233445566'
SIM_ID = 'sim_112233445566'
RUN_ID = 'run_112233445566'
REPORT_ID = 'report_112233445566'
PROFILE_ID = 'a1b2c3d4e5f60718293a4b5c6d7e8f90'

LEGACY_FLAGS = {
    'LLM_PROFILE_BACKEND': 'sqlite',
    'PROJECT_BACKEND': 'file',
    'SIMULATION_BACKEND': 'file',
    'RUN_BACKEND': 'file',
    'REPORT_BACKEND': 'file',
}
POSTGRES_FLAGS = {name: 'postgres' for name in LEGACY_FLAGS}

#: Lese-Endpunkte je Domäne: Einzelabruf und Liste.
ENDPOINTS = (
    '/api/settings/llm-profiles',
    f'/api/graph/project/{PROJECT_ID}',
    '/api/graph/project/list',
    f'/api/simulation/{SIM_ID}',
    f'/api/simulation/list?project_id={PROJECT_ID}',
    f'/api/runs/{RUN_ID}',
    f'/api/runs?simulation_id={SIM_ID}',
    f'/api/report/{REPORT_ID}',
    f'/api/report/by-simulation/{SIM_ID}',
    f'/api/report/list?simulation_id={SIM_ID}',
)


# -- Umgebung ------------------------------------------------------------------


@pytest.fixture
def database(postgres_database_url: str, monkeypatch) -> Iterator[Database]:
    """Wegwerf-Datenbank auf dem Head, als Prozess-Adapter eingehängt."""
    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    config = AlembicConfig(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    command.upgrade(config, 'head')
    db = Database(postgres_database_url)
    monkeypatch.setattr(session_module, '_database', db)
    monkeypatch.setattr(Config, 'DATABASE_URL', postgres_database_url)
    try:
        yield db
    finally:
        db.dispose()


@pytest.fixture
def paths(tmp_path: Path, monkeypatch) -> dict[str, Path]:
    """Alle Ablagen auf ``tmp_path`` — kein Test schreibt ins echte uploads/."""
    uploads = tmp_path / 'uploads'
    instance = tmp_path / 'instance'
    data = tmp_path / 'data'
    for directory in (uploads, instance, data):
        directory.mkdir()
    monkeypatch.setenv('AGORA_DATA_DIR', str(data))
    monkeypatch.setenv('AGORA_SECRET_KEY', Fernet.generate_key().decode())
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(uploads))
    monkeypatch.setattr(Config, 'OASIS_SIMULATION_DATA_DIR', str(uploads / 'simulations'))
    monkeypatch.setattr(ProjectManager, 'PROJECTS_DIR', str(uploads / 'projects'))
    monkeypatch.setattr(SimulationManager, 'SIMULATION_DATA_DIR', str(uploads / 'simulations'))
    monkeypatch.setattr(RunRegistry, 'REGISTRY_DIR', str(uploads / 'run_registry'))
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(uploads / 'reports'))
    monkeypatch.setattr(
        'app.services.llm_profiles_store._db_path', lambda: instance / 'llm_profiles.db'
    )
    RunRegistry._instance = None
    yield {'uploads': uploads, 'instance': instance, 'data': data}
    RunRegistry._instance = None


def _startup_env(monkeypatch) -> None:
    """Wie ``tests/test_app_startup_schema_gate.py``: ``create_app`` ohne
    echtes Neo4j/Redis und ohne Embedding-Probe."""
    monkeypatch.setenv('FLASK_DEBUG', 'false')
    monkeypatch.setenv('AGORA_ALLOW_ANONYMOUS', 'true')
    monkeypatch.delenv('AGORA_CORS_ALLOW_ALL', raising=False)
    monkeypatch.setattr(Config, 'DEBUG', False)
    monkeypatch.setattr(Config, 'SECRET_KEY', 'test-secret-key-not-a-placeholder')
    monkeypatch.setattr(Config, 'NEO4J_PASSWORD', 'test-neo4j-password')
    monkeypatch.setattr(
        'app.storage.embedding_service.validate_embedding_configuration',
        lambda skip_probe=False: 768,
    )


# -- Legacy-Bestand --------------------------------------------------------------


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


@pytest.fixture
def bestand(paths: dict[str, Path]) -> dict[str, Path]:
    """Je ein Datensatz aus allen fünf Domänen, wie ihn Agora heute schreibt.

    Liefert die Metadateien, die in der Postgres-Phase versteckt werden."""
    uploads = paths['uploads']
    project = Project(
        project_id=PROJECT_ID,
        name='Rollback-Projekt',
        status='graph_completed',
        graph_id='graph_1',
        simulation_requirement='Wie reagieren Stakeholder auf X?',
        created_at='2026-09-01T10:00:00',
        updated_at='2026-09-01T10:30:00',
    )
    simulation = SimulationRecord(
        simulation_id=SIM_ID,
        project_id=PROJECT_ID,
        graph_id='graph_1',
        status='completed',
        entities_count=4,
        profiles_count=4,
        entity_types=['Person', 'Behörde'],
        current_round=3,
        created_at='2026-09-01T11:00:00',
        updated_at='2026-09-01T12:00:00',
        root_simulation_id=SIM_ID,
    )
    run_manifest = {
        'run_id': RUN_ID,
        'run_type': 'simulation_run',
        'entity_id': SIM_ID,
        'parent_run_id': None,
        'status': 'completed',
        'progress': 100,
        'message': 'Simulation abgeschlossen',
        'message_key': None,
        'error': None,
        'started_at': '2026-09-01T11:30:00',
        'updated_at': '2026-09-01T12:00:00',
        'completed_at': '2026-09-01T12:00:00',
        'artifacts': {},
        'resume_capability': {'available': False},
        'branch_label': None,
        'metadata': {'project_id': PROJECT_ID},
        'linked_ids': {'simulation_id': SIM_ID, 'project_id': PROJECT_ID},
        'events': [
            {
                'timestamp': '2026-09-01T11:30:00',
                'type': 'created',
                'status': 'pending',
                'progress': 0,
                'message': '',
                'error': None,
                'details': {},
            }
        ],
    }
    report = ReportRecord(
        report_id=REPORT_ID,
        simulation_id=SIM_ID,
        graph_id='graph_1',
        simulation_requirement='Wie reagieren Stakeholder auf X?',
        status='completed',
        outline={
            'title': 'Bericht',
            'summary': 'Zusammenfassung',
            'sections': [
                {'title': title, 'content': description, 'description': description}
                for title, description in DEFAULT_REPORT_SECTIONS
            ],
        },
        markdown_content='# Bericht\n\nText mit Umlauten: äöü',
        created_at='2026-09-01T13:00:00',
        completed_at='2026-09-01T13:05:00',
    )

    files = {
        'project': uploads / 'projects' / PROJECT_ID / 'project.json',
        'simulation': uploads / 'simulations' / SIM_ID / 'state.json',
        'run': uploads / 'run_registry' / f'{RUN_ID}.json',
        'report': uploads / 'reports' / REPORT_ID / 'meta.json',
        'llm_profiles': paths['instance'] / 'llm_profiles.db',
    }
    _write_json(files['project'], project.to_dict())
    _write_json(files['simulation'], simulation.to_dict())
    _write_json(files['run'], run_manifest)
    _write_json(files['report'], report.to_dict())

    conn = sqlite3.connect(files['llm_profiles'])
    conn.execute(
        'CREATE TABLE llm_profiles (id TEXT PRIMARY KEY, name TEXT NOT NULL, '
        'provider TEXT NOT NULL, base_url TEXT NOT NULL, model_name TEXT NOT NULL, '
        "api_key TEXT NOT NULL DEFAULT '', is_default INTEGER NOT NULL DEFAULT 0, "
        'created_at TEXT NOT NULL, updated_at TEXT NOT NULL)'
    )
    conn.execute(
        'INSERT INTO llm_profiles VALUES (?,?,?,?,?,?,?,?,?)',
        (
            PROFILE_ID, 'Rollback-Profil', 'ollama', 'http://ollama:11434/v1',
            'qwen3', 'KEY-ROLLBACK', 1,
            '2026-03-01T08:00:00+00:00', '2026-03-02T09:00:00+00:00',
        ),
    )
    conn.commit()
    conn.close()
    return files


# -- Ablauf ----------------------------------------------------------------------


def _migrate_and_verify(paths: dict[str, Path], files: dict[str, Path], capsys) -> None:
    """Schritt 2: jedes Skript überträgt ohne Fehler, jedes ``--verify`` gibt 0."""
    uploads = paths['uploads']
    llm = ['--db', str(files['llm_profiles']), '--data-dir', str(paths['data'])]
    runs = [
        (migrate_llm, llm),
        (migrate_projects, ['--projects-dir', str(uploads / 'projects')]),
        (migrate_simulations, ['--simulations-dir', str(uploads / 'simulations')]),
        (migrate_runs, ['--registry-dir', str(uploads / 'run_registry')]),
        (migrate_reports, ['--reports-dir', str(uploads / 'reports')]),
    ]
    for skript, args in runs:
        assert skript.main(args) == 0, f'{skript.__name__}: {capsys.readouterr().out}'
    for skript, args in runs:
        assert skript.main([*args, '--verify']) == 0, (
            f'{skript.__name__} --verify: {capsys.readouterr().out}'
        )


def _clear_run_cache() -> None:
    """Leert den Cache der Registry, die die Route tatsächlich benutzt.

    ``app.api.runs`` hält ``run_registry`` als Modulobjekt. ``RunRegistry._instance
    = None`` hätte nur künftige Konstruktoraufrufe betroffen, und die
    Legacy-Phase hätte das Manifest aus der PostgreSQL-Phase aus dem Cache
    geliefert (Codex-Review auf #1609). Das Repository wählt ``_repo`` bei jedem
    Zugriff neu; ohne Cache liest die Route also über den gerade gesetzten
    Schalter.
    """
    from app.api import runs as runs_api

    for registry in (runs_api.run_registry, RunRegistry._instance):
        if registry is not None:
            registry._cache.clear()


def _collect(
    monkeypatch, flags: dict[str, str], before_request: Callable[[str], None] | None = None
) -> dict[str, Any]:
    """Startet eine frische App mit ``flags`` und sammelt alle Antworten."""
    for name, value in flags.items():
        monkeypatch.setattr(Config, name, value)
    _clear_run_cache()

    from app import create_app

    client = create_app().test_client()
    responses: dict[str, Any] = {}
    for endpoint in ENDPOINTS:
        if before_request is not None:
            before_request(endpoint)
        response = client.get(endpoint)
        assert response.status_code == 200, f'{endpoint}: {response.get_data(as_text=True)}'
        responses[endpoint] = response.get_json()
    return responses


def _hide(files: dict[str, Path]) -> None:
    for path in files.values():
        path.rename(path.with_name(path.name + '.versteckt'))


def _restore(files: dict[str, Path]) -> None:
    for path in files.values():
        path.with_name(path.name + '.versteckt').rename(path)


def test_migrate_switch_to_postgres_and_roll_back_without_loss(
    database, paths, bestand, monkeypatch, capsys
):
    _startup_env(monkeypatch)
    _migrate_and_verify(paths, bestand, capsys)

    # Schritt 3: Postgres überall, Legacy-Metadaten weg.
    _hide(bestand)
    from_postgres = _collect(monkeypatch, POSTGRES_FLAGS)
    assert not bestand['run'].exists()  # auch nichts neu in die Datei geschrieben
    _restore(bestand)

    # Schritt 4: zurück auf Legacy. Der Spion belegt, dass der Einzelabruf des
    # Runs am Cache vorbei über das Datei-Repository läuft — sonst verglichen
    # wir die PostgreSQL-Antwort mit sich selbst (Codex-Review auf #1609).
    from app.services.file_run_store import FileRunRepository

    single_run = f'/api/runs/{RUN_ID}'
    current = {'endpoint': ''}
    cache_hits: list[bool] = []
    file_reads: list[str] = []
    original_read = RunRegistry._read_run
    original_get = FileRunRepository.get

    def spy_read(self, run_id):
        if current['endpoint'] == single_run and run_id == RUN_ID:
            cache_hits.append(run_id in self._cache)
        return original_read(self, run_id)

    def spy_get(self, run_id):
        if current['endpoint'] == single_run:
            file_reads.append(run_id)
        return original_get(self, run_id)

    def note_endpoint(endpoint: str) -> None:
        current['endpoint'] = endpoint

    monkeypatch.setattr(RunRegistry, '_read_run', spy_read)
    monkeypatch.setattr(FileRunRepository, 'get', spy_get)
    from_legacy = _collect(monkeypatch, LEGACY_FLAGS, before_request=note_endpoint)
    assert cache_hits and cache_hits[0] is False, 'Einzelabruf kam aus dem Cache'
    assert RUN_ID in file_reads

    for endpoint in ENDPOINTS:
        assert from_postgres[endpoint] == from_legacy[endpoint], endpoint

    # Kein Datenverlust: jeder Datensatz ist nach dem Rückweg da, mit
    # unveränderten Kennungen und Zeitstempeln.
    profiles = from_legacy['/api/settings/llm-profiles']['data']['profiles']
    assert [(p['id'], p['name']) for p in profiles] == [(PROFILE_ID, 'Rollback-Profil')]
    project = from_legacy[f'/api/graph/project/{PROJECT_ID}']['data']
    assert (project['project_id'], project['updated_at']) == (PROJECT_ID, '2026-09-01T10:30:00')
    simulation = from_legacy[f'/api/simulation/{SIM_ID}']['data']
    assert (simulation['simulation_id'], simulation['status']) == (SIM_ID, 'completed')
    run = from_legacy[f'/api/runs/{RUN_ID}']['data']
    assert (run['run_id'], run['status']) == (RUN_ID, 'completed')
    report = from_legacy[f'/api/report/{REPORT_ID}']['data']
    assert (report['report_id'], report['status']) == (REPORT_ID, 'completed')


def test_rollback_order_is_enforced_at_startup(monkeypatch):
    """Rückweg in falscher Reihenfolge: Simulationen zurück, Runs und Reports
    noch auf ``postgres`` — ``Config.validate()`` muss den Start verweigern."""
    monkeypatch.setattr(Config, 'DATABASE_URL', 'postgresql+psycopg://u:p@host:5432/db')
    for name, value in POSTGRES_FLAGS.items():
        monkeypatch.setattr(Config, name, value)
    monkeypatch.setattr(Config, 'SIMULATION_BACKEND', 'file')

    errors = Config.validate()

    assert any('AGORA_RUN_BACKEND=postgres requires' in e for e in errors)
    assert any('AGORA_REPORT_BACKEND=postgres requires' in e for e in errors)
