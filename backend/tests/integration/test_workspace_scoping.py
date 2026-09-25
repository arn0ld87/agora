"""Workspace-Isolation der Metadaten (ADR-0018, Issue #1614).

Geprüft gegen PostgreSQL:

* der Backfill eines vorhandenen Bestands auf den Default-Workspace (der
  Produktivpfad nach #1592) samt ``alembic check`` und Rückweg,
* zusammengesetzte Fremdschlüssel: kein Verweis über Workspace-Grenzen,
* Request-Kontext: Lesen, Listen, Schreiben und Löschen nur im eigenen
  Workspace; ohne Principal ein Fehler,
* System-Kontext: neue Zeilen erben den Workspace ihres Elternteils,
* die zentrale Verweisprüfung im Guard für Supabase-Nutzer.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Iterator

import jwt
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from flask import Blueprint, Flask, jsonify
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import WORKSPACE_SCOPED_BACKENDS, Config
from app.contracts import Project
from app.contracts.auth_contract import AuthType, Principal
from app.contracts.report_record_contract import ReportRecord
from app.contracts.run_record_contract import RunRecord
from app.contracts.simulation_record_contract import SimulationRecord
from app.contracts.workspace_contract import DEFAULT_WORKSPACE_ID, WorkspaceRole
from app.infrastructure.postgres import session as session_module
from app.infrastructure.postgres.repositories.project_repository import (
    PostgresProjectRepository,
    ProjectNotStored,
)
from app.infrastructure.postgres.repositories.report_repository import (
    PostgresReportRepository,
)
from app.infrastructure.postgres.repositories.run_repository import PostgresRunRepository
from app.infrastructure.postgres.repositories.simulation_repository import (
    PostgresSimulationRepository,
)
from app.infrastructure.postgres.repositories.workspace_repository import (
    PostgresWorkspaceRepository,
)
from app.infrastructure.postgres.session import Database
from app.infrastructure.postgres.workspace_scope import (
    RecordInOtherWorkspace,
    WorkspaceScopeMissing,
)
from app.security import principal_context
from app.security.principal_context import set_principal
from app.utils.auth import install_blueprint_guard

pytestmark = pytest.mark.integration

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / 'migrations'
BEFORE_SCOPING = '5c2913c7ba4f'
ISSUER = 'https://supabase.example.test/auth/v1'
SECRET = 's' * 40
ALICE = uuid.UUID('a11ce000-0000-4000-8000-000000000001')
BOB = uuid.UUID('b0b00000-0000-4000-8000-000000000002')


def _alembic() -> AlembicConfig:
    config = AlembicConfig(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    return config


@pytest.fixture
def database(postgres_database_url: str, monkeypatch) -> Iterator[Database]:
    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    command.upgrade(_alembic(), 'head')
    db = Database(postgres_database_url)
    monkeypatch.setattr(session_module, '_database', db)
    monkeypatch.setattr(Config, 'DATABASE_URL', postgres_database_url)
    try:
        yield db
    finally:
        db.dispose()


@pytest.fixture
def workspaces(database):
    repo = PostgresWorkspaceRepository(database=database)
    a = repo.create('Alice', 'alice')
    b = repo.create('Bob', 'bob')
    repo.add_member(a.workspace_id, ALICE, WorkspaceRole.OWNER)
    repo.add_member(b.workspace_id, BOB, WorkspaceRole.OWNER)
    return a.workspace_id, b.workspace_id


def _principal(workspace_id: uuid.UUID, user: uuid.UUID = ALICE) -> Principal:
    return Principal(
        auth_type=AuthType.JWT,
        user_id=user,
        workspace_id=workspace_id,
        roles=frozenset({WorkspaceRole.OWNER}),
    )


@pytest.fixture
def as_workspace():
    """Kontextmanager: ein Request mit dem Principal des Workspace."""
    app = Flask(__name__)

    def enter(workspace_id: uuid.UUID):
        ctx = app.test_request_context('/')
        ctx.push()
        set_principal(_principal(workspace_id))
        return ctx

    return enter


def _project(project_id: str) -> Project:
    return Project(project_id=project_id, name='P', created_at='2026-09-01T10:00:00', updated_at='2026-09-01T10:00:00')


def _simulation(simulation_id: str, project_id: str) -> SimulationRecord:
    return SimulationRecord(
        simulation_id=simulation_id,
        project_id=project_id,
        graph_id='g',
        created_at='2026-09-01T11:00:00',
        updated_at='2026-09-01T11:00:00',
    )


def _report(report_id: str, simulation_id: str) -> ReportRecord:
    return ReportRecord(
        report_id=report_id,
        simulation_id=simulation_id,
        graph_id='g',
        simulation_requirement='Frage',
        status='completed',
    )


def _run(run_id: str, simulation_id: str) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        run_type='simulation',
        entity_id=simulation_id,
        linked_ids={'simulation_id': simulation_id},
        status='completed',
    )


def _workspace_of(database: Database, table: str, key: str) -> uuid.UUID:
    queries = {
        'projects': 'SELECT workspace_id FROM agora.projects WHERE id = :k',
        'simulations': 'SELECT workspace_id FROM agora.simulations WHERE id = :k',
        'runs': 'SELECT workspace_id FROM agora.runs WHERE id = :k',
        'reports': 'SELECT workspace_id FROM agora.reports WHERE id = :k',
    }
    with database.session() as session:
        return session.execute(text(queries[table]), {'k': key}).scalar_one()


# -- Migration ---------------------------------------------------------------------


def test_existing_rows_are_backfilled_to_the_default_workspace(postgres_database_url, monkeypatch):
    """Der Produktivpfad: Bestand ohne Workspace → Default-Workspace, danach
    kein Drift, und der Rückweg nimmt die Spalten wieder heraus."""
    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    command.upgrade(_alembic(), BEFORE_SCOPING)
    db = Database(postgres_database_url)
    try:
        with db.session() as session:
            session.execute(text(
                "INSERT INTO agora.projects (id, name, status, created_at, updated_at, payload) "
                "VALUES ('proj_bestand0001', 'P', 'created', '2026', '2026', '{}')"
            ))
            session.execute(text(
                "INSERT INTO agora.simulations (id, project_id, graph_id, status, created_at, updated_at, payload) "
                "VALUES ('sim_bestand00001', 'proj_bestand0001', 'g', 'created', '2026', '2026', '{}')"
            ))
            session.execute(text(
                "INSERT INTO agora.runs (id, simulation_id, payload) "
                "VALUES ('run_bestand00001', 'sim_bestand00001', '{}')"
            ))
            session.execute(text(
                "INSERT INTO agora.reports (id, report_id, simulation_id, status, payload) "
                "VALUES ('report_bestand01', 'report_bestand01', 'sim_bestand00001', 'completed', '{}')"
            ))

        command.upgrade(_alembic(), 'head')
        command.check(_alembic())

        for table, key in (
            ('projects', 'proj_bestand0001'),
            ('simulations', 'sim_bestand00001'),
            ('runs', 'run_bestand00001'),
            ('reports', 'report_bestand01'),
        ):
            assert _workspace_of(db, table, key) == DEFAULT_WORKSPACE_ID, table

        command.downgrade(_alembic(), BEFORE_SCOPING)
        with db.session() as session:
            columns = session.execute(text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema = 'agora' AND column_name = 'workspace_id' "
                "AND table_name IN ('projects', 'simulations', 'runs', 'reports')"
            )).scalar_one()
        assert columns == 0
        command.upgrade(_alembic(), 'head')
        command.check(_alembic())
    finally:
        db.dispose()


def test_references_cannot_cross_workspaces(database, workspaces):
    ws_a, ws_b = workspaces
    PostgresProjectRepository(database=database).add_existing(_project('proj_aaaaaaaa0001'), ws_a)

    with pytest.raises(IntegrityError), database.session() as session:
        session.execute(
            text(
                "INSERT INTO agora.simulations (id, project_id, graph_id, status, created_at, "
                "updated_at, payload, workspace_id) VALUES ('sim_fremd0000001', "
                "'proj_aaaaaaaa0001', 'g', 'created', 'x', 'x', '{}', :ws)"
            ),
            {'ws': str(ws_b)},
        )


def test_deleting_a_project_keeps_the_simulation_workspace(database, workspaces):
    ws_a, _ = workspaces
    projects = PostgresProjectRepository(database=database)
    projects.add_existing(_project('proj_aaaaaaaa0002'), ws_a)
    PostgresSimulationRepository(database=database).add_existing(
        _simulation('sim_aaaaaaaa0002', 'proj_aaaaaaaa0002')
    )

    assert projects.delete('proj_aaaaaaaa0002') is True

    with database.session() as session:
        row = session.execute(text(
            "SELECT project_id, workspace_id FROM agora.simulations WHERE id = 'sim_aaaaaaaa0002'"
        )).one()
    assert (row.project_id, row.workspace_id) == (None, ws_a)


# -- System-Kontext --------------------------------------------------------------


def test_system_context_inherits_the_parent_workspace(database, workspaces):
    ws_a, _ = workspaces
    PostgresProjectRepository(database=database).add_existing(_project('proj_aaaaaaaa0003'), ws_a)
    simulations = PostgresSimulationRepository(database=database)
    simulations.save(_simulation('sim_aaaaaaaa0003', 'proj_aaaaaaaa0003'))
    PostgresRunRepository(database=database).save(_run('run_aaaaaaaa0003', 'sim_aaaaaaaa0003'))
    PostgresReportRepository(database=database).save(_report('report_aaaaaa03', 'sim_aaaaaaaa0003'))

    assert _workspace_of(database, 'simulations', 'sim_aaaaaaaa0003') == ws_a
    assert _workspace_of(database, 'runs', 'run_aaaaaaaa0003') == ws_a
    assert _workspace_of(database, 'reports', 'report_aaaaaa03') == ws_a


def test_a_new_project_without_request_lands_in_the_default_workspace(database):
    project = PostgresProjectRepository(database=database).create('Hintergrund')

    assert _workspace_of(database, 'projects', project.project_id) == DEFAULT_WORKSPACE_ID


# -- Request-Kontext -------------------------------------------------------------


def test_requests_see_only_their_own_workspace(database, workspaces, as_workspace):
    ws_a, ws_b = workspaces
    projects = PostgresProjectRepository(database=database)
    simulations = PostgresSimulationRepository(database=database)
    runs = PostgresRunRepository(database=database)
    reports = PostgresReportRepository(database=database)

    ctx = as_workspace(ws_a)
    try:
        own = projects.create('A')
        simulations.save(_simulation('sim_aaaaaaaa0004', own.project_id))
        runs.save(_run('run_aaaaaaaa0004', 'sim_aaaaaaaa0004'))
        reports.save(_report('report_aaaaaa04', 'sim_aaaaaaaa0004'))
    finally:
        ctx.pop()

    ctx = as_workspace(ws_b)
    try:
        assert projects.get(own.project_id) is None
        assert projects.list() == []
        assert simulations.get('sim_aaaaaaaa0004') is None
        assert simulations.list() == []
        assert runs.get('run_aaaaaaaa0004') is None
        assert runs.list_all() == []
        assert reports.get('report_aaaaaa04') is None
        assert reports.list() == [] and reports.list_ids() == []
        # Schreiben und Löschen über die Grenze scheitern, ohne etwas zu ändern.
        with pytest.raises(ProjectNotStored):
            projects.save(own)
        with pytest.raises(RecordInOtherWorkspace):
            simulations.save(_simulation('sim_aaaaaaaa0004', own.project_id))
        with pytest.raises(RecordInOtherWorkspace):
            runs.save(_run('run_aaaaaaaa0004', 'sim_aaaaaaaa0004'))
        with pytest.raises(RecordInOtherWorkspace):
            reports.save(_report('report_aaaaaa04', 'sim_aaaaaaaa0004'))
        assert projects.delete(own.project_id) is False
        assert reports.delete('report_aaaaaa04') is False
    finally:
        ctx.pop()

    ctx = as_workspace(ws_a)
    try:
        assert [p.project_id for p in projects.list()] == [own.project_id]
        assert [s.simulation_id for s in simulations.list()] == ['sim_aaaaaaaa0004']
        assert [r.run_id for r in runs.list_all()] == ['run_aaaaaaaa0004']
        assert reports.list_ids() == ['report_aaaaaa04']
    finally:
        ctx.pop()


def test_a_simulation_cannot_point_at_a_foreign_project(database, workspaces, as_workspace):
    from app.infrastructure.postgres.repositories.simulation_repository import (
        SimulationProjectMissing,
    )

    ws_a, ws_b = workspaces
    PostgresProjectRepository(database=database).add_existing(_project('proj_aaaaaaaa0005'), ws_a)

    ctx = as_workspace(ws_b)
    try:
        with pytest.raises(SimulationProjectMissing):
            PostgresSimulationRepository(database=database).save(
                _simulation('sim_bbbbbbbb0005', 'proj_aaaaaaaa0005')
            )
    finally:
        ctx.pop()


def test_a_request_without_principal_is_an_error_in_tenant_mode(database, monkeypatch):
    """Im Tenant-Modus (JWT aktiv) ist ein Request ohne Principal ein
    Programmierfehler; einmandantig gilt der System-Kontext."""
    repo = PostgresProjectRepository(database=database)
    with Flask(__name__).test_request_context('/'):
        assert repo.list() == []

    monkeypatch.setattr(
        'app.infrastructure.postgres.workspace_scope.tenant_mode_active', lambda: True
    )
    with Flask(__name__).test_request_context('/'):
        with pytest.raises(WorkspaceScopeMissing):
            repo.list()


# -- Zentrale Verweisprüfung im Guard --------------------------------------------


@pytest.fixture
def guarded_client(database, workspaces, monkeypatch):
    monkeypatch.setattr(Config, 'AUTH_BACKEND', 'hybrid')
    monkeypatch.setattr(Config, 'SUPABASE_JWT_ISSUER', ISSUER)
    monkeypatch.setattr(Config, 'SUPABASE_JWT_SECRET', SECRET)
    monkeypatch.setattr(Config, 'SUPABASE_JWKS_URL', '')
    for _, attr in WORKSPACE_SCOPED_BACKENDS:
        monkeypatch.setattr(Config, attr, 'postgres')
    monkeypatch.delenv('AGORA_ALLOW_ANONYMOUS', raising=False)
    principal_context.reset_jwt_verifier()

    bp = Blueprint(f'probe_{uuid.uuid4().hex}', __name__)

    @bp.route('/simulation/<simulation_id>')
    def by_path(simulation_id):
        return jsonify({'ok': simulation_id})

    @bp.route('/start', methods=['POST'])
    def by_body():
        return jsonify({'ok': True})

    @bp.route('/list')
    def by_query():
        return jsonify({'ok': True})

    @bp.route('/report/<report_id>/progress')
    def report_progress(report_id):
        return jsonify({'ok': report_id})

    @bp.route('/status', methods=['POST'])
    def task_status():
        return jsonify({'ok': True})

    install_blueprint_guard(bp)
    app = Flask(__name__)
    app.register_blueprint(bp, url_prefix='/api')
    yield app.test_client()
    principal_context.reset_jwt_verifier()


def _bearer(user: uuid.UUID) -> dict[str, str]:
    now = int(time.time())
    token = jwt.encode(
        {'sub': str(user), 'iss': ISSUER, 'aud': 'authenticated', 'iat': now, 'exp': now + 600},
        SECRET,
        algorithm='HS256',
    )
    return {'Authorization': f'Bearer {token}'}


def test_guard_rejects_foreign_ids_in_path_body_and_query(database, workspaces, guarded_client):
    ws_a, _ = workspaces
    PostgresProjectRepository(database=database).add_existing(_project('proj_aaaaaaaa0006'), ws_a)
    PostgresSimulationRepository(database=database).add_existing(
        _simulation('sim_aaaaaaaa0006', 'proj_aaaaaaaa0006')
    )

    # Alice: eigene Kennungen gehen durch.
    assert guarded_client.get('/api/simulation/sim_aaaaaaaa0006', headers=_bearer(ALICE)).status_code == 200
    assert guarded_client.post(
        '/api/start', json={'simulation_id': 'sim_aaaaaaaa0006'}, headers=_bearer(ALICE)
    ).status_code == 200

    # Bob: dieselben Kennungen sind für ihn nicht vorhanden.
    for response in (
        guarded_client.get('/api/simulation/sim_aaaaaaaa0006', headers=_bearer(BOB)),
        guarded_client.post('/api/start', json={'simulation_id': 'sim_aaaaaaaa0006'}, headers=_bearer(BOB)),
        guarded_client.post('/api/start', json={'simulation_ids': ['sim_aaaaaaaa0006']}, headers=_bearer(BOB)),
        guarded_client.get('/api/list?project_id=proj_aaaaaaaa0006', headers=_bearer(BOB)),
    ):
        assert (response.status_code, response.get_json()['code']) == (404, 'not_found')

    # Eine unbekannte Kennung sieht genauso aus wie eine fremde.
    unknown = guarded_client.get('/api/simulation/sim_gibtesnicht01', headers=_bearer(ALICE))
    assert unknown.status_code == 404


def test_guard_leaves_operators_unchecked(database, workspaces, guarded_client, monkeypatch):
    monkeypatch.setenv('AGORA_AUTH_TOKEN', 'master-token-for-tests')

    response = guarded_client.get(
        '/api/simulation/sim_gibtesnicht01', headers={'X-Agora-Token': 'master-token-for-tests'}
    )

    assert response.status_code == 200



def test_pending_report_is_reachable_for_its_owner_but_a_foreign_one_is_not(
    database, workspaces, guarded_client
):
    """Ein Report existiert bis zum Ende der Erzeugung nur als Dateien; sein
    Besitzer fragt ihn trotzdem ab (Codex-Review auf #1623). Ein gespeicherter
    Report eines anderen Workspace bleibt 404."""
    ws_a, _ = workspaces
    PostgresProjectRepository(database=database).add_existing(_project('proj_aaaaaaaa0007'), ws_a)
    PostgresSimulationRepository(database=database).add_existing(
        _simulation('sim_aaaaaaaa0007', 'proj_aaaaaaaa0007')
    )
    PostgresReportRepository(database=database).add_existing(
        'report_gespeichert', _report('report_gespeichert', 'sim_aaaaaaaa0007')
    )

    pending = guarded_client.get('/api/report/report_laeuft0001/progress', headers=_bearer(BOB))
    assert pending.status_code == 200
    foreign = guarded_client.get('/api/report/report_gespeichert/progress', headers=_bearer(BOB))
    assert foreign.status_code == 404
    own = guarded_client.get('/api/report/report_gespeichert/progress', headers=_bearer(ALICE))
    assert own.status_code == 200


def test_task_status_is_bound_to_the_workspace(database, workspaces, guarded_client):
    """Status-Endpunkte lesen In-Memory-Tasks per ``task_id`` aus dem Body
    (Codex-Review auf #1623). Ein laufender Report-Task mit noch
    ungespeicherter ``report_id`` gehört seinem Besitzer."""
    from app.models.task import TaskManager

    ws_a, _ = workspaces
    PostgresProjectRepository(database=database).add_existing(_project('proj_aaaaaaaa0008'), ws_a)
    PostgresSimulationRepository(database=database).add_existing(
        _simulation('sim_aaaaaaaa0008', 'proj_aaaaaaaa0008')
    )
    task_id = TaskManager().create_task(
        'report_generate',
        metadata={'simulation_id': 'sim_aaaaaaaa0008', 'report_id': 'report_laeuft0002'},
    )

    own = guarded_client.post('/api/status', json={'task_id': task_id}, headers=_bearer(ALICE))
    foreign = guarded_client.post('/api/status', json={'task_id': task_id}, headers=_bearer(BOB))

    assert own.status_code == 200
    assert (foreign.status_code, foreign.get_json()['code']) == (404, 'not_found')


def test_task_visibility_ignores_unsaved_outputs_but_not_foreign_anchors(database, workspaces):
    from app.security.resource_guard import task_visible

    ws_a, ws_b = workspaces
    PostgresProjectRepository(database=database).add_existing(_project('proj_aaaaaaaa0009'), ws_a)
    PostgresProjectRepository(database=database).add_existing(_project('proj_bbbbbbbb0009'), ws_b)

    assert task_visible({'project_id': 'proj_aaaaaaaa0009', 'report_id': 'report_neu'}, ws_a)
    assert not task_visible({'project_id': 'proj_aaaaaaaa0009', 'report_id': 'report_neu'}, ws_b)
    assert not task_visible({'project_id': 'proj_aaaaaaaa0009', 'simulation_id': None}, ws_b)
    assert not task_visible({'report_id': 'report_neu'}, ws_a)  # kein gespeicherter Anker
    assert not task_visible(
        {'project_id': 'proj_aaaaaaaa0009', 'graph_id': 'x', 'simulation_id': 'sim_fremd'}, ws_b
    )
