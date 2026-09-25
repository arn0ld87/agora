"""Der PostgreSQL-Adapter muss dieselben Zusagen halten wie der Dateiadapter.

Referenz ist ``backend/tests/contracts/test_run_repository_contract.py``; die
Zusagen werden hier gegen eine echte PostgreSQL-Instanz nachgezogen.

Der wichtigste Test ist der Roundtrip über **alle** Vertragsfelder, inklusive
des Unterschieds zwischen "Feld fehlt" und "Feld steht auf ``null``"
(``RunRecord.to_manifest`` nutzt ``exclude_unset``). Dazu kommt der
Fremdschlüssel auf ``agora.simulations``, den der Dateiadapter nicht kennt,
und der Resume-Pfad ``POST /api/runs/<id>/resume`` mit Postgres-Backend.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from flask import Flask
from sqlalchemy import text

from app.config import Config
from app.contracts import Project
from app.contracts.job_lease_contract import JobLease
from app.contracts.run_record_contract import RunRecord
from app.contracts.simulation_record_contract import SimulationRecord
from app.infrastructure.postgres.repositories.project_repository import (
    PostgresProjectRepository,
)
from app.infrastructure.postgres.repositories.run_repository import (
    PostgresRunRepository,
    RunSimulationMissing,
)
from app.infrastructure.postgres.repositories.simulation_repository import (
    PostgresSimulationRepository,
)
from app.infrastructure.postgres.session import Database
from app.repositories.run_repository import RunRepository

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = BACKEND_DIR / 'migrations'

PROJECT_ID = 'proj_aaaabbbbcccc'
SIM_A = 'sim_aaaa00000001'
SIM_B = 'sim_bbbb00000001'


def _alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    return config


@pytest.fixture
def migrated_db(postgres_database_url: str, monkeypatch) -> Iterator[Database]:
    """Wegwerf-Datenbank mit ``alembic upgrade head``, einem Projekt und zwei
    Simulationen."""
    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    command.upgrade(_alembic_config(), 'head')
    database = Database(postgres_database_url)
    PostgresProjectRepository(database=database).add_existing(
        Project(
            project_id=PROJECT_ID,
            name='Projekt',
            created_at='2026-09-01T10:00:00',
            updated_at='2026-09-01T10:00:00',
        )
    )
    simulations = PostgresSimulationRepository(database=database)
    for simulation_id in (SIM_A, SIM_B):
        simulations.add_existing(
            SimulationRecord(
                simulation_id=simulation_id,
                project_id=PROJECT_ID,
                graph_id='graph_1',
                created_at='2026-09-01T11:00:00',
                updated_at='2026-09-01T11:00:00',
            )
        )
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def repo(migrated_db: Database) -> PostgresRunRepository:
    return PostgresRunRepository(database=migrated_db)


def _record(
    run_id: str,
    *,
    updated_at: str = '2026-09-02T10:00:00',
    simulation_id: str | None = SIM_A,
    **extra: Any,
) -> RunRecord:
    linked: dict[str, Any] = {'project_id': PROJECT_ID}
    if simulation_id is not None:
        linked['simulation_id'] = simulation_id
    return RunRecord(
        run_id=run_id,
        run_type='simulation_run',
        entity_id=simulation_id or 'graph_1',
        status='processing',
        started_at='2026-09-02T09:00:00',
        updated_at=updated_at,
        linked_ids=linked,
        **extra,
    )


def _full_manifest() -> dict[str, Any]:
    """Jedes Vertragsfeld abweichend vom Vorgabewert belegt, plus ein
    Zusatzfeld (``extra="allow"``) und Lease-Felder im ``metadata``."""
    return {
        'run_id': 'run_voll00000001',
        'run_type': 'report_generate',
        'entity_id': 'report_äöü',
        'parent_run_id': 'run_eltern000001',
        'replayed_from_run_id': 'run_quelle000001',
        'status': 'completed',
        'progress': 100,
        'message': 'Fertig mit "Anführungszeichen"',
        'message_key': 'run.report_completed',
        'error': 'Fehlertext',
        'started_at': '2026-09-02T08:15:00.123456',
        'updated_at': '2026-09-02T09:00:00',
        'completed_at': '2026-09-02T09:00:00',
        'branch_label': 'Variante B',
        'termination_reason': 'completed',
        'artifacts': {'report_id': 'report_1', 'paths': ['a.json', 'b.md']},
        'resume_capability': {'available': True, 'action': 'resume'},
        'metadata': {
            'owner_pid': 4242,
            'owner_token': 'tok',
            'heartbeat_at': '2026-09-02T08:59:00+00:00',
            'lease_ttl_s': 90,
            'nested': {'zahl': 1.5, 'liste': [1, None, 'x']},
        },
        'linked_ids': {'simulation_id': SIM_A, 'project_id': PROJECT_ID},
        'events': [
            {
                'timestamp': '2026-09-02T08:15:00',
                'type': 'created',
                'status': 'pending',
                'progress': 0,
                'message': '',
                'error': None,
                'details': {},
            }
        ],
        'zukunftsfeld': {'aus': 'einer neueren Version'},
    }


# -- Port und Roundtrip ------------------------------------------------------


def test_adapter_satisfies_the_port(repo):
    assert isinstance(repo, RunRepository)


def test_roundtrip_over_every_contract_field(repo):
    manifest = _full_manifest()
    record = RunRecord(**manifest)
    repo.save(record)

    loaded = repo.get(record.run_id)

    assert loaded is not None
    assert loaded.to_manifest() == manifest
    # Sicherstellen, dass der Test wirklich jedes Vertragsfeld belegt.
    assert set(RunRecord.model_fields) <= set(manifest)


def test_unset_fields_stay_unset_and_explicit_nulls_stay_null(repo):
    """``to_manifest`` unterscheidet "fehlt" von "``null``" — die Ablage auch."""
    sparse = RunRecord(run_id='run_duenn0000001', status='pending', error=None)
    repo.save(sparse)

    loaded = repo.get('run_duenn0000001')

    assert loaded is not None
    assert loaded.to_manifest() == {
        'run_id': 'run_duenn0000001',
        'status': 'pending',
        'error': None,
    }


def test_save_returns_the_record_and_does_not_stamp(repo):
    record = _record('run_stempel00001', updated_at='2026-01-01T00:00:00')

    assert repo.save(record) is record
    loaded = repo.get('run_stempel00001')
    assert loaded is not None and loaded.updated_at == '2026-01-01T00:00:00'


def test_save_creates_then_overwrites(repo):
    record = _record('run_upd000000001')
    repo.save(record)
    record.status = 'completed'
    record.progress = 100
    record.metadata = {'neu': True}
    repo.save(record)

    loaded = repo.get('run_upd000000001')
    assert loaded is not None
    assert loaded.status == 'completed'
    assert loaded.metadata == {'neu': True}


def test_get_returns_none_for_unknown_id(repo):
    assert repo.get('run_gibtesnicht0') is None


def test_projected_columns_follow_the_manifest(repo, migrated_db):
    repo.save(RunRecord(**_full_manifest()))

    with migrated_db.session() as session:
        row = session.execute(
            text(
                'SELECT run_type, entity_id, status, simulation_id, '
                'started_at, updated_at, completed_at '
                "FROM agora.runs WHERE id = 'run_voll00000001'"
            )
        ).one()
    assert tuple(row) == (
        'report_generate',
        'report_äöü',
        'completed',
        SIM_A,
        '2026-09-02T08:15:00.123456',
        '2026-09-02T09:00:00',
        '2026-09-02T09:00:00',
    )


# -- list_all ----------------------------------------------------------------


def test_list_all_returns_newest_updated_first(repo):
    repo.save(_record('run_alt000000001', updated_at='2026-09-01T00:00:00'))
    repo.save(_record('run_neu000000001', updated_at='2026-09-03T00:00:00'))
    repo.save(_record('run_mitte0000001', updated_at='2026-09-02T00:00:00'))

    assert [r.run_id for r in repo.list_all()] == [
        'run_neu000000001',
        'run_mitte0000001',
        'run_alt000000001',
    ]


def test_list_all_falls_back_to_started_at(repo):
    """Sortierschlüssel wie im Dateiadapter: ``updated_at or started_at``."""
    repo.save(RunRecord(run_id='run_nurstart0001', started_at='2026-09-05T00:00:00'))
    repo.save(_record('run_mitupdate001', updated_at='2026-09-04T00:00:00'))
    repo.save(RunRecord(run_id='run_ohnezeit0001'))

    assert [r.run_id for r in repo.list_all()] == [
        'run_nurstart0001',
        'run_mitupdate001',
        'run_ohnezeit0001',
    ]


def test_list_all_is_empty_without_rows(repo):
    assert repo.list_all() == []


def test_list_all_respects_limit(repo):
    for day in range(1, 6):
        repo.save(_record(f'run_limit0000{day:03d}', updated_at=f'2026-09-0{day}T00:00:00'))

    assert [r.run_id for r in repo.list_all(limit=2)] == [
        'run_limit0000005',
        'run_limit0000004',
    ]
    assert repo.list_all(limit=0) == []


def test_unreadable_row_is_skipped_before_the_limit(repo, migrated_db):
    """``limit=1`` liefert den neuesten **lesbaren** Run."""
    repo.save(_record('run_gut000000001', updated_at='2026-09-01T00:00:00'))
    with migrated_db.session() as session:
        session.execute(
            text(
                'INSERT INTO agora.runs (id, updated_at, payload) '
                "VALUES ('run_kaputt000001', '2026-09-09T00:00:00', "
                '\'{"run_id": "run_kaputt000001", "progress": "keine Zahl"}\'::jsonb)'
            )
        )

    assert repo.get('run_kaputt000001') is None
    assert [r.run_id for r in repo.list_all(limit=1)] == ['run_gut000000001']
    assert [r.run_id for r in repo.list_all()] == ['run_gut000000001']


# -- Fremdschlüssel auf agora.simulations --------------------------------------


def test_run_without_simulation_is_stored_with_null(repo, migrated_db):
    """Graph-Build-Runs haben keine Simulation."""
    repo.save(_record('run_graph0000001', simulation_id=None))

    with migrated_db.session() as session:
        stored = session.execute(
            text("SELECT simulation_id FROM agora.runs WHERE id = 'run_graph0000001'")
        ).scalar_one()
    assert stored is None
    assert repo.get('run_graph0000001') is not None


def test_new_run_with_unknown_simulation_is_rejected_not_dropped(repo):
    with pytest.raises(RunSimulationMissing):
        repo.save(_record('run_waise0000001', simulation_id='sim_gibtesnicht0'))
    with pytest.raises(RunSimulationMissing):
        repo.add_existing(_record('run_waise0000002', simulation_id='sim_gibtesnicht0'))
    assert repo.get('run_waise0000001') is None
    assert repo.get('run_waise0000002') is None


def test_deleting_the_simulation_detaches_its_runs(repo, migrated_db):
    """``ON DELETE SET NULL``: die Run-Historie überlebt die Simulation, der
    Verweis im Manifest bleibt erhalten."""
    repo.save(_record('run_haengtdran01', simulation_id=SIM_B))
    with migrated_db.session() as session:
        session.execute(text(f"DELETE FROM agora.simulations WHERE id = '{SIM_B}'"))

    loaded = repo.get('run_haengtdran01')
    assert loaded is not None
    assert loaded.linked_ids['simulation_id'] == SIM_B
    with migrated_db.session() as session:
        stored = session.execute(
            text("SELECT simulation_id FROM agora.runs WHERE id = 'run_haengtdran01'")
        ).scalar_one()
    assert stored is None


def test_cached_manifest_still_saves_after_simulation_deletion(repo, migrated_db):
    """``RunRegistry`` hält das Manifest im Cache. Wird die Simulation
    währenddessen gelöscht, trägt der nächste ``save`` den alten Verweis —
    er darf daran nicht scheitern (Lehre aus dem Codex-Review auf #1598)."""
    cached = _record('run_laeuftnoch01', simulation_id=SIM_B)
    repo.save(cached)
    with migrated_db.session() as session:
        session.execute(text(f"DELETE FROM agora.simulations WHERE id = '{SIM_B}'"))

    cached.status = 'completed'
    repo.save(cached)

    loaded = repo.get('run_laeuftnoch01')
    assert loaded is not None
    assert loaded.status == 'completed'
    assert loaded.linked_ids['simulation_id'] == SIM_B


def test_add_existing_is_idempotent_and_does_not_overwrite(repo):
    manifest = _full_manifest()
    assert repo.add_existing(RunRecord(**manifest)) is True

    changed = RunRecord(**{**manifest, 'status': 'failed'})
    assert repo.add_existing(changed) is False

    loaded = repo.get(manifest['run_id'])
    assert loaded is not None
    assert loaded.status == 'completed'


def test_add_existing_counts_a_detached_run_as_existing(repo, migrated_db):
    """Codex-Review auf #1605: wurde die Simulation nach der ersten Migration
    gelöscht, muss eine Wiederholung den Run als "schon da" melden, nicht mit
    ``RunSimulationMissing`` scheitern."""
    record = _record('run_wiederholt01', simulation_id=SIM_B)
    assert repo.add_existing(record) is True
    with migrated_db.session() as session:
        session.execute(text(f"DELETE FROM agora.simulations WHERE id = '{SIM_B}'"))

    assert repo.add_existing(record) is False


@pytest.mark.parametrize('payload', ['1', 'true', '"text"', '[1, 2]', 'null'])
def test_non_object_payload_counts_as_unreadable(repo, migrated_db, payload):
    """Codex-Review auf #1605: die JSONB-Spalte erzwingt kein Objekt. Ein
    Skalar darf ``get``/``list_all`` nicht abbrechen."""
    repo.save(_record('run_gut000000002', updated_at='2026-09-01T00:00:00'))
    with migrated_db.session() as session:
        session.execute(
            text(
                'INSERT INTO agora.runs (id, updated_at, payload) '
                "VALUES ('run_skalar000001', '2026-09-09T00:00:00', "
                f"'{payload}'::jsonb)"
            )
        )

    assert repo.get('run_skalar000001') is None
    assert [r.run_id for r in repo.list_all()] == ['run_gut000000002']


# -- Alembic ---------------------------------------------------------------


def test_the_migration_can_be_taken_back(postgres_database_url, monkeypatch):
    """Der Rückweg aus dem Runbook muss laufen: ``downgrade c4e8a1d93b56``
    entfernt nur ``agora.runs``; Modell und Migration bleiben deckungsgleich."""
    from sqlalchemy import create_engine, inspect

    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    config = _alembic_config()

    command.upgrade(config, 'head')
    command.check(config)
    engine = create_engine(postgres_database_url)
    try:
        assert 'runs' in inspect(engine).get_table_names(schema='agora')

        command.downgrade(config, 'c4e8a1d93b56')
        tabellen = inspect(engine).get_table_names(schema='agora')
        assert 'runs' not in tabellen
        assert 'simulations' in tabellen

        command.upgrade(config, 'head')
        assert 'runs' in inspect(engine).get_table_names(schema='agora')
    finally:
        engine.dispose()


# -- Resume mit Postgres-Backend --------------------------------------------


@pytest.fixture
def postgres_registry(migrated_db, monkeypatch, tmp_path):
    """``RunRegistry`` mit ``AGORA_RUN_BACKEND=postgres`` gegen die Testdatenbank.

    Das Registry-Verzeichnis zeigt auf ein leeres ``tmp_path``: bleibt es
    leer, beweist das, dass nichts in die Datei geschrieben wurde.
    """
    from app.infrastructure.postgres import session as session_module
    from app.services.run_registry import RunRegistry

    registry_dir = tmp_path / 'run_registry'
    monkeypatch.setattr(Config, 'RUN_BACKEND', 'postgres')
    monkeypatch.setattr(RunRegistry, 'REGISTRY_DIR', str(registry_dir))
    monkeypatch.setattr(session_module, '_database', migrated_db)
    RunRegistry._instance = None
    try:
        yield RunRegistry(), registry_dir
    finally:
        RunRegistry._instance = None


def _resume_client():
    from app.api import runs_bp
    from app.services.artifact_store import InMemoryArtifactStore

    app = Flask(__name__)
    app.extensions = {'artifact_store': InMemoryArtifactStore()}
    app.register_blueprint(runs_bp, url_prefix='/api/runs')
    return app.test_client()


def _lease(age_seconds: int) -> dict[str, Any]:
    return JobLease(
        owner_pid=os.getpid(),
        owner_token='egal',
        heartbeat_at=datetime.now(UTC) - timedelta(seconds=age_seconds),
        lease_ttl_s=90,
    ).to_metadata()


def test_resume_keeps_the_lease_guard_with_postgres_backend(postgres_registry):
    """409 ``job_lease_active`` bleibt; die Lease liegt im Manifest in
    PostgreSQL, nicht in einer Datei."""
    registry, registry_dir = postgres_registry
    run = registry.create_run(
        run_type='graph_build',
        entity_id=PROJECT_ID,
        status='processing',
        linked_ids={'project_id': PROJECT_ID, 'graph_id': 'graph_1'},
        metadata=_lease(age_seconds=0),
    )
    RunRegistry = type(registry)
    RunRegistry._instance = None  # Cache verwerfen: gelesen wird aus PostgreSQL

    with patch(
        'app.api.runs._resume_or_restart_graph_build',
        return_value={'path': 'dispatched'},
    ) as dispatch:
        response = _resume_client().post(f"/api/runs/{run['run_id']}/resume")

    assert response.status_code == 409
    assert response.get_json()['code'] == 'job_lease_active'
    dispatch.assert_not_called()
    assert not registry_dir.exists() or list(registry_dir.iterdir()) == []


def test_resume_dispatches_with_expired_lease_and_postgres_backend(postgres_registry):
    registry, registry_dir = postgres_registry
    run = registry.create_run(
        run_type='graph_build',
        entity_id=PROJECT_ID,
        status='processing',
        linked_ids={'project_id': PROJECT_ID, 'graph_id': 'graph_1'},
        metadata=_lease(age_seconds=999),
    )
    type(registry)._instance = None

    with patch(
        'app.api.runs._resume_or_restart_graph_build',
        return_value={'path': 'dispatched'},
    ) as dispatch:
        response = _resume_client().post(f"/api/runs/{run['run_id']}/resume")

    assert response.status_code == 200
    assert response.get_json()['data'] == {'path': 'dispatched'}
    dispatch.assert_called_once()
    assert not registry_dir.exists() or list(registry_dir.iterdir()) == []


def test_registry_update_run_writes_through_to_postgres(postgres_registry, repo):
    """``update_run`` inklusive Event-Anhang landet in ``agora.runs``."""
    registry, _ = postgres_registry
    run = registry.create_run(
        run_type='simulation_run',
        entity_id=SIM_A,
        linked_ids={'simulation_id': SIM_A, 'project_id': PROJECT_ID},
    )
    registry.update_run(run['run_id'], status='completed', progress=100, message='ok')

    stored = repo.get(run['run_id'])
    assert stored is not None
    assert stored.status == 'completed'
    assert stored.completed_at is not None
    assert [event['type'] for event in stored.events] == ['created', 'updated']
    assert registry.list_runs(simulation_id=SIM_A)[0]['run_id'] == run['run_id']
