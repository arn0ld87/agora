"""PostgreSQL-Adapter des ``WorkspaceRepository``-Ports (Issue #1612,
docs/plans/supabase.md PR 5).

``add_member`` legt eine Mitgliedschaft an oder aktualisiert ihre Rolle
(``INSERT ... ON CONFLICT DO UPDATE`` auf dem Primärschlüssel
``(workspace_id, user_id)``) — derselbe Zweiweg-Schreibpfad wie beim
Report-Adapter, nur ohne Fremdschlüssel-Sonderfall.

``create`` wirft ``WorkspaceSlugTaken`` bei einem doppelten Slug. Der
``IntegrityError`` wird gezielt auf den Unique-Constraint-Namen
(``uq_workspaces_slug``) geprüft, damit ein anderer Integritätsfehler nicht
stillschweigend verschluckt wird.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from ....contracts.workspace_contract import Workspace, WorkspaceMembership, WorkspaceRole
from ..models.workspace import WorkspaceMemberModel, WorkspaceModel
from ..session import Database, get_database


class WorkspaceSlugTaken(ValueError):
    """``create`` wurde mit einem Slug aufgerufen, der schon vergeben ist."""


def _is_slug_violation(exc: IntegrityError) -> bool:
    return 'uq_workspaces_slug' in str(exc.orig)


def _to_workspace(row: WorkspaceModel) -> Workspace:
    return Workspace(
        workspace_id=row.id,
        name=row.name,
        slug=row.slug,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_membership(row: WorkspaceMemberModel) -> WorkspaceMembership:
    return WorkspaceMembership(
        workspace_id=row.workspace_id,
        user_id=row.user_id,
        role=WorkspaceRole(row.role),
        created_at=row.created_at,
    )


class PostgresWorkspaceRepository:
    """Workspaces und Mitgliedschaften in ``agora.workspaces``/
    ``agora.workspace_members``."""

    def __init__(self, database: Optional[Database] = None) -> None:
        self._database = database

    @property
    def db(self) -> Database:
        # Erst beim Zugriff auflösen: ein konstruiertes, aber ungenutztes
        # Repository soll keine Verbindung aufbauen.
        return self._database or get_database()

    # -- Workspaces ------------------------------------------------------

    def get(self, workspace_id: uuid.UUID) -> Optional[Workspace]:
        with self.db.session() as session:
            row = session.get(WorkspaceModel, workspace_id)
            return None if row is None else _to_workspace(row)

    def get_by_slug(self, slug: str) -> Optional[Workspace]:
        with self.db.session() as session:
            row = session.scalar(
                select(WorkspaceModel).where(WorkspaceModel.slug == slug)
            )
            return None if row is None else _to_workspace(row)

    def create(self, name: str, slug: str) -> Workspace:
        new_id = uuid.uuid4()
        try:
            with self.db.session() as session:
                row = WorkspaceModel(id=new_id, name=name, slug=slug)
                session.add(row)
                session.flush()
                workspace = _to_workspace(row)
        except IntegrityError as exc:
            if _is_slug_violation(exc):
                raise WorkspaceSlugTaken(f"slug '{slug}' is already taken") from exc
            raise
        return workspace

    def list_for_user(self, user_id: uuid.UUID) -> List[Workspace]:
        with self.db.session() as session:
            rows = session.scalars(
                select(WorkspaceModel)
                .join(
                    WorkspaceMemberModel,
                    WorkspaceMemberModel.workspace_id == WorkspaceModel.id,
                )
                .where(WorkspaceMemberModel.user_id == user_id)
                .order_by(WorkspaceModel.created_at)
            ).all()
            return [_to_workspace(row) for row in rows]

    # -- Mitgliedschaften --------------------------------------------------

    def membership(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[WorkspaceMembership]:
        with self.db.session() as session:
            row = session.get(WorkspaceMemberModel, (workspace_id, user_id))
            return None if row is None else _to_membership(row)

    def add_member(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, role: WorkspaceRole
    ) -> WorkspaceMembership:
        with self.db.session() as session:
            statement = insert(WorkspaceMemberModel).values(
                workspace_id=workspace_id,
                user_id=user_id,
                role=role.value,
            )
            statement = statement.on_conflict_do_update(
                index_elements=[
                    WorkspaceMemberModel.workspace_id,
                    WorkspaceMemberModel.user_id,
                ],
                set_={'role': statement.excluded.role},
            )
            session.execute(statement)
            row = session.get(WorkspaceMemberModel, (workspace_id, user_id))
            assert row is not None
            return _to_membership(row)

    def remove_member(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        with self.db.session() as session:
            row = session.get(WorkspaceMemberModel, (workspace_id, user_id))
            if row is None:
                return False
            session.delete(row)
            return True
