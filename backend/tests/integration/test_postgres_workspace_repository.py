"""Der PostgreSQL-Adapter fuer Workspaces gegen eine echte Instanz
(Issue #1612, docs/plans/supabase.md PR 5).

Schwerpunkte: Default-Workspace nach der Migration, Slug-Eindeutigkeit,
Rollen-Constraint, Mitgliedschaften (anlegen/aktualisieren/entfernen),
Kaskadenloeschung und der Alembic-Rueckweg.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Iterator

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.contracts.workspace_contract import WorkspaceRole
from app.infrastructure.postgres.models.workspace import DEFAULT_WORKSPACE_ID
from app.infrastructure.postgres.repositories.workspace_repository import (
    PostgresWorkspaceRepository,
    WorkspaceSlugTaken,
)
from app.infrastructure.postgres.session import Database
from app.repositories.workspace_repository import WorkspaceRepository

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = BACKEND_DIR / 'migrations'


def _alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    return config


@pytest.fixture
def migrated_db(postgres_database_url: str, monkeypatch) -> Iterator[Database]:
    """Wegwerf-Datenbank mit ``alembic upgrade head``."""
    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    command.upgrade(_alembic_config(), 'head')
    database = Database(postgres_database_url)
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def repo(migrated_db: Database) -> PostgresWorkspaceRepository:
    return PostgresWorkspaceRepository(database=migrated_db)


# -- Port und Default-Workspace ----------------------------------------------


def test_adapter_satisfies_the_port(repo):
    assert isinstance(repo, WorkspaceRepository)


def test_default_workspace_exists_after_upgrade(repo):
    workspace = repo.get(DEFAULT_WORKSPACE_ID)

    assert workspace is not None
    assert workspace.workspace_id == DEFAULT_WORKSPACE_ID
    assert workspace.slug == 'default'
    assert workspace.name == 'Standard'


def test_get_returns_none_for_unknown_id(repo):
    assert repo.get(uuid.uuid4()) is None


# -- Erzeugen und Lesen -------------------------------------------------------


def test_create_get_and_get_by_slug_roundtrip(repo):
    created = repo.create(name='Team A', slug='team-a')

    by_id = repo.get(created.workspace_id)
    by_slug = repo.get_by_slug('team-a')

    assert by_id is not None and by_id == created
    assert by_slug is not None and by_slug == created


def test_get_by_slug_returns_none_for_unknown_slug(repo):
    assert repo.get_by_slug('gibt-es-nicht') is None


def test_duplicate_slug_is_rejected(repo):
    repo.create(name='Team A', slug='team-a')

    with pytest.raises(WorkspaceSlugTaken):
        repo.create(name='Team A (zweiter Versuch)', slug='team-a')


@pytest.mark.parametrize(
    'invalid_slug',
    ['', 'Team-A', '-team-a', 'team_a', 'a' * 64],
)
def test_invalid_slug_is_rejected_by_the_database(
    repo, migrated_db, invalid_slug
):
    with pytest.raises(IntegrityError):
        with migrated_db.session() as session:
            session.execute(
                text(
                    "INSERT INTO agora.workspaces (id, name, slug) "
                    "VALUES (:id, 'X', :slug)"
                ),
                {'id': str(uuid.uuid4()), 'slug': invalid_slug},
            )


def test_empty_name_is_rejected_by_the_database(migrated_db):
    with pytest.raises(IntegrityError):
        with migrated_db.session() as session:
            session.execute(
                text(
                    "INSERT INTO agora.workspaces (id, name, slug) "
                    "VALUES (:id, '', 'leer')"
                ),
                {'id': str(uuid.uuid4())},
            )


# -- Mitgliedschaften ----------------------------------------------------------


def test_add_member_creates_then_updates_role(repo):
    workspace = repo.create(name='Team B', slug='team-b')
    user_id = uuid.uuid4()

    created = repo.add_member(workspace.workspace_id, user_id, WorkspaceRole.MEMBER)
    assert created.role == WorkspaceRole.MEMBER

    updated = repo.add_member(workspace.workspace_id, user_id, WorkspaceRole.ADMIN)
    assert updated.role == WorkspaceRole.ADMIN

    fetched = repo.membership(workspace.workspace_id, user_id)
    assert fetched is not None and fetched.role == WorkspaceRole.ADMIN


def test_membership_returns_none_when_absent(repo):
    workspace = repo.create(name='Team C', slug='team-c')
    assert repo.membership(workspace.workspace_id, uuid.uuid4()) is None


def test_invalid_role_is_rejected_by_the_database(repo, migrated_db):
    workspace = repo.create(name='Team D', slug='team-d')

    with pytest.raises(IntegrityError):
        with migrated_db.session() as session:
            session.execute(
                text(
                    'INSERT INTO agora.workspace_members '
                    '(workspace_id, user_id, role) '
                    "VALUES (:workspace_id, :user_id, 'superadmin')"
                ),
                {
                    'workspace_id': str(workspace.workspace_id),
                    'user_id': str(uuid.uuid4()),
                },
            )


def test_list_for_user_returns_only_workspaces_with_membership(repo):
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    workspace_a = repo.create(name='Team E', slug='team-e')
    workspace_b = repo.create(name='Team F', slug='team-f')
    repo.create(name='Team G', slug='team-g')  # keine Mitgliedschaft

    repo.add_member(workspace_a.workspace_id, user_id, WorkspaceRole.OWNER)
    repo.add_member(workspace_b.workspace_id, user_id, WorkspaceRole.VIEWER)
    repo.add_member(workspace_b.workspace_id, other_user_id, WorkspaceRole.OWNER)

    found = {w.workspace_id for w in repo.list_for_user(user_id)}

    assert found == {workspace_a.workspace_id, workspace_b.workspace_id}


def test_list_for_user_returns_empty_for_unknown_user(repo):
    assert repo.list_for_user(uuid.uuid4()) == []


def test_remove_member_returns_true_then_false(repo):
    workspace = repo.create(name='Team H', slug='team-h')
    user_id = uuid.uuid4()
    repo.add_member(workspace.workspace_id, user_id, WorkspaceRole.MEMBER)

    assert repo.remove_member(workspace.workspace_id, user_id) is True
    assert repo.remove_member(workspace.workspace_id, user_id) is False
    assert repo.membership(workspace.workspace_id, user_id) is None


def test_deleting_a_workspace_cascades_members(repo, migrated_db):
    workspace = repo.create(name='Team I', slug='team-i')
    user_id = uuid.uuid4()
    repo.add_member(workspace.workspace_id, user_id, WorkspaceRole.MEMBER)

    with migrated_db.session() as session:
        session.execute(
            text('DELETE FROM agora.workspaces WHERE id = :id'),
            {'id': str(workspace.workspace_id)},
        )

    with migrated_db.session() as session:
        remaining = session.execute(
            text(
                'SELECT count(*) FROM agora.workspace_members '
                'WHERE workspace_id = :id'
            ),
            {'id': str(workspace.workspace_id)},
        ).scalar_one()
    assert remaining == 0


# -- Alembic -------------------------------------------------------------


def test_the_migration_can_be_taken_back(postgres_database_url, monkeypatch):
    """Der Rueckweg aus dem Runbook muss laufen: ``downgrade 8d6e0b3c2f15``
    entfernt nur Workspace-Tabellen; Modell und Migration bleiben
    deckungsgleich."""
    from sqlalchemy import create_engine, inspect

    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    config = _alembic_config()

    command.upgrade(config, 'head')
    command.check(config)
    engine = create_engine(postgres_database_url)
    try:
        tabellen = inspect(engine).get_table_names(schema='agora')
        assert 'workspaces' in tabellen
        assert 'workspace_members' in tabellen

        command.downgrade(config, '8d6e0b3c2f15')
        tabellen = inspect(engine).get_table_names(schema='agora')
        assert 'workspaces' not in tabellen
        assert 'workspace_members' not in tabellen
        assert 'reports' in tabellen

        command.upgrade(config, 'head')
        tabellen = inspect(engine).get_table_names(schema='agora')
        assert 'workspaces' in tabellen
        assert 'workspace_members' in tabellen
    finally:
        engine.dispose()
