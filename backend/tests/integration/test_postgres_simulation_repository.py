"""Der PostgreSQL-Adapter muss dieselben Zusagen halten wie der Dateiadapter.

Referenz ist ``backend/tests/contracts/test_simulation_repository_contract.py``;
die Zusagen werden hier gegen eine echte PostgreSQL-Instanz nachgezogen.

Der wichtigste Test ist der Roundtrip über **alle** Vertragsfelder: der
Spaltenschnitt trennt Kernspalten von einem ``payload``, und genau dort könnte
ein Feld verlorengehen. Dazu kommt der Fremdschlüssel auf ``agora.projects``,
den der Dateiadapter nicht kennt.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.contracts import Project
from app.contracts.simulation_record_contract import SimulationRecord
from app.infrastructure.postgres.repositories.project_repository import (
    PostgresProjectRepository,
)
from app.infrastructure.postgres.repositories.simulation_repository import (
    PostgresSimulationRepository,
    SimulationProjectMissing,
)
from app.infrastructure.postgres.session import Database
from app.repositories.simulation_repository import SimulationRepository

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = BACKEND_DIR / 'migrations'

PROJECT_A = 'proj_aaaabbbbcccc'
PROJECT_B = 'proj_ddddeeeeffff'


@pytest.fixture
def migrated_db(postgres_database_url: str, monkeypatch) -> Iterator[Database]:
    """Wegwerf-Datenbank mit ``alembic upgrade head`` und zwei Projekten."""
    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    config = Config(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    command.upgrade(config, 'head')
    database = Database(postgres_database_url)
    projects = PostgresProjectRepository(database=database)
    for project_id in (PROJECT_A, PROJECT_B):
        projects.add_existing(
            Project(
                project_id=project_id,
                name=project_id,
                created_at='2026-09-01T10:00:00',
                updated_at='2026-09-01T10:00:00',
            )
        )
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def repo(migrated_db: Database) -> PostgresSimulationRepository:
    return PostgresSimulationRepository(database=migrated_db)


def _record(
    simulation_id: str,
    project_id: str = PROJECT_A,
    root_simulation_id: Optional[str] = None,
    source_simulation_id: Optional[str] = None,
) -> SimulationRecord:
    now = datetime.now().isoformat()
    return SimulationRecord(
        simulation_id=simulation_id,
        project_id=project_id,
        graph_id='graph_001',
        created_at=now,
        updated_at=now,
        root_simulation_id=root_simulation_id or simulation_id,
        source_simulation_id=source_simulation_id,
    )


def _full_record() -> SimulationRecord:
    """Jedes Vertragsfeld abweichend vom Vorgabewert belegt."""
    return SimulationRecord(
        simulation_id='sim_voll00000001',
        project_id=PROJECT_A,
        graph_id='graph_äöü',
        enable_twitter=False,
        enable_reddit=False,
        status='completed',
        entities_count=42,
        profiles_count=17,
        entity_types=['Person', 'Organisation', 'Behörde'],
        config_generated=True,
        config_reasoning='Begründung mit "Anführungszeichen" und Umlauten',
        current_round=12,
        twitter_status='completed',
        reddit_status='failed',
        created_at='2026-09-02T08:15:00.123456',
        updated_at='2026-09-02T09:00:00',
        error='Fehlertext',
        source_simulation_id='sim_quelle000001',
        root_simulation_id='sim_wurzel000001',
        branch_name='Variante B',
        branch_depth=3,
        persona_floor=25,
    )


def test_adapter_satisfies_the_port(repo):
    assert isinstance(repo, SimulationRepository)


def test_roundtrip_over_every_contract_field(repo):
    record = _full_record()
    repo.add_existing(record)

    loaded = repo.get(record.simulation_id)

    assert loaded is not None
    assert loaded.to_dict() == record.to_dict()
    # Sicherstellen, dass der Test wirklich jedes Feld belegt.
    assert set(record.to_dict()) == set(SimulationRecord.model_fields)


def test_save_creates_an_unknown_simulation(repo):
    """``create_simulation`` schreibt den ersten Datensatz über ``save``."""
    record = _record('sim_neu000000001')
    repo.save(record)

    loaded = repo.get('sim_neu000000001')
    assert loaded is not None
    assert loaded.project_id == PROJECT_A


def test_save_updates_and_advances_updated_at(repo):
    record = _record('sim_upd000000001')
    record.updated_at = '2026-01-01T00:00:00'
    repo.add_existing(record)

    record.status = 'running'
    repo.save(record)

    loaded = repo.get('sim_upd000000001')
    assert loaded is not None
    assert loaded.status == 'running'
    assert loaded.updated_at > '2026-01-01T00:00:00'


def test_get_returns_none_for_unknown_id(repo):
    assert repo.get('sim_gibtesnicht00') is None


def test_list_all_and_filtered_by_project(repo):
    repo.save(_record('sim_a00000000001', project_id=PROJECT_A))
    repo.save(_record('sim_b00000000001', project_id=PROJECT_B))

    assert {r.simulation_id for r in repo.list()} == {
        'sim_a00000000001',
        'sim_b00000000001',
    }
    assert [r.simulation_id for r in repo.list(project_id=PROJECT_A)] == [
        'sim_a00000000001'
    ]
    assert repo.list(project_id='proj_nichtvorhand') == []


def test_list_is_empty_without_rows(repo):
    assert repo.list() == []


def test_list_branches_returns_family_by_root_id(repo):
    root = 'sim_root00000001'
    repo.save(_record(root))
    repo.save(_record('sim_branch000001', root_simulation_id=root, source_simulation_id=root))
    repo.save(_record('sim_branch000002', root_simulation_id=root, source_simulation_id=root))
    repo.save(_record('sim_unrelated0001'))

    ids = {r.simulation_id for r in repo.list_branches(root)}

    assert ids == {root, 'sim_branch000001', 'sim_branch000002'}
    # Aus Sicht eines Zweigs dieselbe Familie.
    assert {r.simulation_id for r in repo.list_branches('sim_branch000001')} == ids


def test_list_branches_treats_missing_root_as_self(repo):
    """Altbestand ohne ``root_simulation_id``: die Simulation ist ihre eigene Wurzel."""
    record = _record('sim_altbestand01')
    record.root_simulation_id = None
    repo.add_existing(record)

    assert [r.simulation_id for r in repo.list_branches('sim_altbestand01')] == [
        'sim_altbestand01'
    ]


def test_list_branches_is_empty_for_unknown_simulation(repo):
    assert repo.list_branches('sim_gibtesnicht00') == []


def test_empty_project_id_roundtrips_as_null(repo, migrated_db):
    record = _record('sim_ohneprojekt1', project_id='')
    repo.save(record)

    with migrated_db.session() as session:
        stored = session.execute(
            text("SELECT project_id FROM agora.simulations WHERE id = 'sim_ohneprojekt1'")
        ).scalar_one()
    assert stored is None
    loaded = repo.get('sim_ohneprojekt1')
    assert loaded is not None and loaded.project_id == ''


def test_unknown_project_is_rejected_not_dropped(repo):
    with pytest.raises(SimulationProjectMissing):
        repo.save(_record('sim_waise0000001', project_id='proj_gibtesnicht'))
    with pytest.raises(SimulationProjectMissing):
        repo.add_existing(_record('sim_waise0000002', project_id='proj_gibtesnicht'))
    assert repo.get('sim_waise0000001') is None


def test_add_existing_is_idempotent_and_keeps_timestamps(repo):
    record = _full_record()
    assert repo.add_existing(record) is True

    changed = _full_record()
    changed.status = 'failed'
    assert repo.add_existing(changed) is False

    loaded = repo.get(record.simulation_id)
    assert loaded is not None
    assert loaded.status == 'completed'
    assert loaded.updated_at == record.updated_at


def test_deleting_the_project_detaches_its_simulations(repo, migrated_db):
    """``ON DELETE SET NULL``: ``delete_project`` entfernt erst die Artefakte,
    dann die Zeile — ein RESTRICT liesse das Projekt halb gelöscht zurück."""
    repo.save(_record('sim_haengtdran01', project_id=PROJECT_B))

    assert PostgresProjectRepository(database=migrated_db).delete(PROJECT_B) is True

    loaded = repo.get('sim_haengtdran01')
    assert loaded is not None
    assert loaded.project_id == ''


def test_stale_state_after_project_deletion_still_saves(repo, migrated_db):
    """Codex-Review auf #1598: ``SimulationManager`` hält den Zustand im
    Speicher. Wird das Projekt währenddessen gelöscht, trägt der nächste
    ``save`` die alte Projektkennung — er darf daran nicht scheitern, und die
    gelöste Zuordnung bleibt gelöst."""
    stale = _record('sim_laeuftnoch01', project_id=PROJECT_B)
    repo.save(stale)
    assert PostgresProjectRepository(database=migrated_db).delete(PROJECT_B) is True

    stale.status = 'completed'
    repo.save(stale)

    loaded = repo.get('sim_laeuftnoch01')
    assert loaded is not None
    assert loaded.status == 'completed'
    assert loaded.project_id == ''


def test_detached_simulation_can_be_reattached_to_an_existing_project(repo, migrated_db):
    record = _record('sim_neuzuordnen1', project_id=PROJECT_B)
    repo.save(record)
    PostgresProjectRepository(database=migrated_db).delete(PROJECT_B)

    record.project_id = PROJECT_A
    repo.save(record)

    loaded = repo.get('sim_neuzuordnen1')
    assert loaded is not None and loaded.project_id == PROJECT_A


def test_unreadable_row_does_not_break_the_list(repo, migrated_db):
    repo.save(_record('sim_gut000000001'))
    with migrated_db.session() as session:
        session.execute(
            text(
                'INSERT INTO agora.simulations '
                '(id, graph_id, status, created_at, updated_at, payload) '
                "VALUES ('sim_kaputt000001', 'g', 'created', 'x', 'x', "
                "'{\"entities_count\": \"keine Zahl\"}'::jsonb)"
            )
        )

    assert [r.simulation_id for r in repo.list()] == ['sim_gut000000001']


def test_the_migration_can_be_taken_back(postgres_database_url, monkeypatch):
    """Der Rückweg aus dem Runbook muss laufen: ``downgrade 7a3c1e84f209``
    entfernt nur ``agora.simulations``; Modell und Migration bleiben deckungsgleich."""
    from sqlalchemy import create_engine, inspect

    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    config = Config(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))

    command.upgrade(config, 'head')
    command.check(config)
    engine = create_engine(postgres_database_url)
    try:
        assert 'simulations' in inspect(engine).get_table_names(schema='agora')

        command.downgrade(config, '7a3c1e84f209')
        tabellen = inspect(engine).get_table_names(schema='agora')
        assert 'simulations' not in tabellen
        assert 'projects' in tabellen

        command.upgrade(config, 'head')
        assert 'simulations' in inspect(engine).get_table_names(schema='agora')
    finally:
        engine.dispose()
