"""Der PostgreSQL-Adapter muss dieselben Zusagen halten wie der Dateiadapter.

Referenz ist ``backend/tests/contracts/test_persona_set_repository_contract.py``;
die Zusagen werden hier gegen eine echte PostgreSQL-Instanz nachgezogen. Dazu
kommt, was nur die Datenbank kennt: Workspace-Bindung (ADR-0018), Row Level
Security, gleichzeitiges ``mark_used`` über mehrere Verbindungen und der
Migrations-Roundtrip samt ``alembic check``.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Iterator

import pytest
from alembic import command
from alembic.config import Config
from flask import Flask
from sqlalchemy import create_engine, inspect, text

from app.contracts.auth_contract import AuthType, Principal
from app.contracts.persona_set_contract import (
    PersonaSetEntry,
    PersonaSetProfile,
    PersonaSetRecord,
)
from app.contracts.workspace_contract import DEFAULT_WORKSPACE_ID, WorkspaceRole
from app.infrastructure.postgres.repositories.persona_set_repository import (
    PostgresPersonaSetRepository,
)
from app.infrastructure.postgres.repositories.workspace_repository import (
    PostgresWorkspaceRepository,
)
from app.infrastructure.postgres.session import Database
from app.repositories.persona_set_repository import PersonaSetRepository
from app.security.principal_context import set_principal

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = BACKEND_DIR / 'migrations'
BEFORE_PERSONA_SETS = 'dc4e84e7c000'
ALICE = uuid.UUID('a11ce000-0000-4000-8000-000000000001')
BOB = uuid.UUID('b0b00000-0000-4000-8000-000000000002')


def _alembic(url: str, monkeypatch) -> Config:
    monkeypatch.setenv('DATABASE_URL', url)
    config = Config(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    return config


@pytest.fixture
def migrated_db(postgres_database_url: str, monkeypatch) -> Iterator[Database]:
    """Wegwerf-Datenbank mit ``alembic upgrade head``."""
    command.upgrade(_alembic(postgres_database_url, monkeypatch), 'head')
    database = Database(postgres_database_url)
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def repo(migrated_db: Database) -> PostgresPersonaSetRepository:
    return PostgresPersonaSetRepository(database=migrated_db)


def _entry(entry_id: str, origin: str = 'manual') -> PersonaSetEntry:
    return PersonaSetEntry(
        entry_id=entry_id,
        origin=origin,
        profile=PersonaSetProfile(username=f'user_{entry_id}', name=f'Name {entry_id}'),
        source_entity_uuid='uuid-1' if origin == 'graph' else None,
    )


def _record(set_id: str = 'pset_aaaaaaaaaaaa', **overrides) -> PersonaSetRecord:
    data = {
        'id': set_id,
        'name': 'Betroffene',
        'created_at': '2026-10-07T10:00:00',
        'updated_at': '2026-10-07T10:00:00',
    }
    data.update(overrides)
    return PersonaSetRecord(**data)


def _full_record() -> PersonaSetRecord:
    """Jedes Vertragsfeld abweichend vom Vorgabewert belegt."""
    return _record(
        'pset_voll00000001',
        name='Satz äöü "mit Anführungszeichen"',
        description='Beschreibung mit Umlauten äöü',
        graph_id='graph_001',
        project_id='proj_aabbccddeeff',
        entries=[
            _entry('pent_a', 'graph'),
            _entry('pent_b', 'ai_draft'),
            _entry('pent_c', 'fallback'),
        ],
        locked_at='2026-10-07T11:00:00',
        used_by_simulation_ids=['sim_000000000001', 'sim_000000000002'],
        created_at='2026-10-07T09:00:00.123456',
        updated_at='2026-10-07T11:00:00',
    )


# ---------------------------------------------------------------------------
# Dieselben Zusagen wie der Dateiadapter
# ---------------------------------------------------------------------------


def test_adapter_satisfies_the_port(repo):
    assert isinstance(repo, PersonaSetRepository)


def test_get_unknown_returns_none_and_does_not_raise(repo):
    assert repo.get('pset_gibtesnicht') is None


def test_roundtrip_over_every_contract_field(repo):
    """Der Spaltenschnitt trennt Kernspalten von ``payload`` — hier ginge ein Feld verloren."""
    record = _full_record()
    # Ein gesperrter Satz mit Nutzung kommt über ``save`` nicht hinein (die
    # Sperre ändert nur ``mark_used``); der Roundtrip läuft deshalb über
    # eine Zeile, die der Test direkt anlegt.
    with repo.db.session() as session:
        from app.infrastructure.postgres.models.persona_set import PersonaSetModel
        from app.infrastructure.postgres.repositories.persona_set_repository import (
            _to_row_values,
        )

        session.add(
            PersonaSetModel(**_to_row_values(record), workspace_id=DEFAULT_WORKSPACE_ID)
        )

    loaded = repo.get(record.id)

    assert loaded is not None
    assert loaded.model_dump(mode='json') == record.model_dump(mode='json')
    assert set(record.model_dump()) == set(PersonaSetRecord.model_fields)


def test_save_creates_an_unknown_set_and_stamps_updated_at(repo):
    record = _record()

    repo.save(record)

    loaded = repo.get(record.id)
    assert loaded is not None
    assert loaded.name == 'Betroffene'
    assert loaded.created_at == '2026-10-07T10:00:00'
    assert loaded.updated_at == record.updated_at != '2026-10-07T10:00:00'


def test_save_overwrites_an_existing_set(repo):
    record = _record()
    repo.save(record)

    record.name = 'Neu benannt'
    record.entries = [_entry('pent_a')]
    repo.save(record)

    loaded = repo.get(record.id)
    assert loaded is not None
    assert loaded.name == 'Neu benannt'
    assert [e.entry_id for e in loaded.entries] == ['pent_a']
    assert len(repo.list()) == 1


def test_list_of_empty_table_is_empty(repo):
    assert repo.list() == []


def test_list_is_newest_first_with_id_as_tie_break(repo):
    repo.save(_record('pset_old', created_at='2026-10-01T10:00:00'))
    repo.save(_record('pset_new', created_at='2026-10-03T10:00:00'))
    repo.save(_record('pset_mid_a', created_at='2026-10-02T10:00:00'))
    repo.save(_record('pset_mid_b', created_at='2026-10-02T10:00:00'))

    assert [r.id for r in repo.list()] == ['pset_new', 'pset_mid_b', 'pset_mid_a', 'pset_old']


def test_delete_reports_whether_a_set_existed(repo):
    repo.save(_record())

    assert repo.delete('pset_aaaaaaaaaaaa') is True
    assert repo.get('pset_aaaaaaaaaaaa') is None
    assert repo.delete('pset_aaaaaaaaaaaa') is False


def test_mark_used_locks_on_first_use_and_records_the_simulation(repo):
    repo.save(_record())

    result = repo.mark_used('pset_aaaaaaaaaaaa', 'sim_000000000001')

    assert result is not None
    assert result.used_by_simulation_ids == ['sim_000000000001']
    assert result.locked_at is not None
    stored = repo.get('pset_aaaaaaaaaaaa')
    assert stored is not None
    assert stored.used_by_simulation_ids == ['sim_000000000001']
    assert stored.locked_at == result.locked_at


def test_mark_used_twice_with_the_same_simulation_is_idempotent(repo):
    repo.save(_record())
    first = repo.mark_used('pset_aaaaaaaaaaaa', 'sim_000000000001')
    assert first is not None

    second = repo.mark_used('pset_aaaaaaaaaaaa', 'sim_000000000001')

    assert second is not None
    assert second.used_by_simulation_ids == ['sim_000000000001']
    assert second.locked_at == first.locked_at
    assert second.updated_at == first.updated_at


def test_a_second_simulation_is_appended_and_the_lock_time_stays(repo):
    repo.save(_record())
    first = repo.mark_used('pset_aaaaaaaaaaaa', 'sim_000000000001')
    assert first is not None

    second = repo.mark_used('pset_aaaaaaaaaaaa', 'sim_000000000002')

    assert second is not None
    assert second.used_by_simulation_ids == ['sim_000000000001', 'sim_000000000002']
    assert second.locked_at == first.locked_at


def test_mark_used_on_unknown_set_returns_none_and_creates_nothing(repo):
    assert repo.mark_used('pset_gibtesnicht', 'sim_000000000001') is None
    assert repo.list() == []


def test_mark_used_rejects_an_empty_simulation_id(repo):
    repo.save(_record())

    with pytest.raises(ValueError):
        repo.mark_used('pset_aaaaaaaaaaaa', '')


def test_save_with_a_stale_record_cannot_lift_the_lock(repo):
    stale = _record()
    repo.save(stale)
    repo.mark_used('pset_aaaaaaaaaaaa', 'sim_000000000001')

    stale.name = 'Aenderung auf altem Stand'
    repo.save(stale)

    stored = repo.get('pset_aaaaaaaaaaaa')
    assert stored is not None
    assert stored.name == 'Aenderung auf altem Stand'
    assert stored.locked_at is not None
    assert stored.used_by_simulation_ids == ['sim_000000000001']
    assert stale.locked_at == stored.locked_at
    assert stale.used_by_simulation_ids == ['sim_000000000001']


def test_a_row_with_a_broken_payload_does_not_break_the_list(repo):
    repo.save(_record('pset_gut000000001', created_at='2026-10-02T10:00:00'))
    with repo.db.session() as session:
        session.execute(
            text(
                'INSERT INTO agora.persona_sets '
                '(id, name, created_at, updated_at, payload, workspace_id) '
                "VALUES ('pset_kaputt00001', 'K', '2026-10-03T10:00:00', 'x', "
                "'{\"entries\": \"keine Liste\"}'::jsonb, "
                "'00000000-0000-0000-0000-000000000001')"
            )
        )

    assert [r.id for r in repo.list()] == ['pset_gut000000001']


# ---------------------------------------------------------------------------
# Was nur die Datenbank kennt
# ---------------------------------------------------------------------------


def test_concurrent_mark_used_over_separate_connections_loses_no_simulation(
    postgres_database_url, repo
):
    repo.save(_record())
    simulation_ids = [f'sim_{i:012d}' for i in range(12)]
    errors: list[BaseException] = []

    def work(simulation_id: str) -> None:
        database = Database(postgres_database_url)
        try:
            PostgresPersonaSetRepository(database=database).mark_used(
                'pset_aaaaaaaaaaaa', simulation_id
            )
        except BaseException as exc:  # noqa: BLE001 — wird unten geprueft
            errors.append(exc)
        finally:
            database.dispose()

    threads = [threading.Thread(target=work, args=(sid,)) for sid in simulation_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    stored = repo.get('pset_aaaaaaaaaaaa')
    assert stored is not None
    assert sorted(stored.used_by_simulation_ids) == simulation_ids
    assert stored.locked_at is not None


def test_graph_and_project_are_plain_references_without_foreign_keys(repo):
    """Der Satz gehört der Bibliothek: Verweise auf fehlende Graphen/Projekte sind erlaubt."""
    repo.save(_record(graph_id='graph_gibtes_nicht', project_id='proj_gibtes_nicht'))

    loaded = repo.get('pset_aaaaaaaaaaaa')
    assert loaded is not None
    assert (loaded.graph_id, loaded.project_id) == ('graph_gibtes_nicht', 'proj_gibtes_nicht')


def test_empty_name_is_rejected_by_the_table(repo):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), repo.db.session() as session:
        session.execute(
            text(
                'INSERT INTO agora.persona_sets '
                '(id, name, created_at, updated_at, payload, workspace_id) '
                "VALUES ('pset_leer0000001', '', 'x', 'x', '{}', "
                "'00000000-0000-0000-0000-000000000001')"
            )
        )


def test_the_table_is_workspace_bound_with_forced_row_level_security(repo):
    with repo.db.session() as session:
        flags = session.execute(
            text(
                'SELECT relrowsecurity, relforcerowsecurity FROM pg_class '
                "WHERE oid = 'agora.persona_sets'::regclass"
            )
        ).one()
        policy = session.execute(
            text(
                'SELECT policyname FROM pg_policies '
                "WHERE schemaname = 'agora' AND tablename = 'persona_sets'"
            )
        ).scalars().all()
        nullable = session.execute(
            text(
                'SELECT is_nullable FROM information_schema.columns '
                "WHERE table_schema = 'agora' AND table_name = 'persona_sets' "
                "AND column_name = 'workspace_id'"
            )
        ).scalar_one()

    assert (flags.relrowsecurity, flags.relforcerowsecurity) == (True, True)
    assert policy == ['agora_workspace_isolation']
    assert nullable == 'NO'


def test_the_table_has_no_member_read_policy_for_authenticated(repo):
    """Personasätze laufen nur über die Flask-API; kein Realtime-Lesezugriff."""
    with repo.db.session() as session:
        names = session.execute(
            text(
                'SELECT policyname FROM pg_policies '
                "WHERE schemaname = 'agora' AND tablename = 'persona_sets' "
                "AND policyname = 'agora_member_read'"
            )
        ).scalars().all()

    assert names == []


@pytest.fixture
def workspaces(migrated_db: Database):
    workspace_repo = PostgresWorkspaceRepository(database=migrated_db)
    a = workspace_repo.create('Alice', 'alice')
    b = workspace_repo.create('Bob', 'bob')
    workspace_repo.add_member(a.workspace_id, ALICE, WorkspaceRole.OWNER)
    workspace_repo.add_member(b.workspace_id, BOB, WorkspaceRole.OWNER)
    return a.workspace_id, b.workspace_id


def _as(workspace_id: uuid.UUID, user: uuid.UUID):
    ctx = Flask(__name__).test_request_context('/')
    ctx.push()
    set_principal(
        Principal(
            auth_type=AuthType.JWT,
            user_id=user,
            workspace_id=workspace_id,
            roles=frozenset({WorkspaceRole.OWNER}),
        )
    )
    return ctx


def test_each_workspace_sees_only_its_own_sets(repo, workspaces):
    ws_a, ws_b = workspaces
    ctx = _as(ws_a, ALICE)
    try:
        repo.save(_record('pset_alice0000001'))
    finally:
        ctx.pop()
    ctx = _as(ws_b, BOB)
    try:
        repo.save(_record('pset_bob000000001'))
    finally:
        ctx.pop()

    ctx = _as(ws_a, ALICE)
    try:
        assert [r.id for r in repo.list()] == ['pset_alice0000001']
        assert repo.get('pset_bob000000001') is None
        assert repo.delete('pset_bob000000001') is False
        assert repo.mark_used('pset_bob000000001', 'sim_000000000001') is None
    finally:
        ctx.pop()

    # Der Zugriff aus dem fremden Workspace hat nichts verändert.
    ctx = _as(ws_b, BOB)
    try:
        stored = repo.get('pset_bob000000001')
        assert stored is not None
        assert stored.used_by_simulation_ids == []
        assert stored.locked_at is None
    finally:
        ctx.pop()


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def test_the_migration_matches_the_model_and_can_be_taken_back(postgres_database_url, monkeypatch):
    """Der Rückweg aus dem Runbook muss laufen: ``downgrade dc4e84e7c000``
    entfernt nur ``agora.persona_sets``; Modell und Migration bleiben deckungsgleich."""
    config = _alembic(postgres_database_url, monkeypatch)
    command.upgrade(config, 'head')
    command.check(config)
    engine = create_engine(postgres_database_url)
    try:
        assert 'persona_sets' in inspect(engine).get_table_names(schema='agora')

        command.downgrade(config, BEFORE_PERSONA_SETS)
        tabellen = inspect(engine).get_table_names(schema='agora')
        assert 'persona_sets' not in tabellen
        assert {'projects', 'simulations', 'runs', 'reports'} <= set(tabellen)

        command.upgrade(config, 'head')
        command.check(config)
        assert 'persona_sets' in inspect(engine).get_table_names(schema='agora')
    finally:
        engine.dispose()
