"""Port fuer Workspaces und Mitgliedschaften (Issue #1612,
docs/plans/supabase.md PR 5).

Anders als die uebrigen Ports dieses Verzeichnisses gibt es hier **keinen**
Dateiadapter und **kein** Backend-Flag: Workspaces sind eine reine
PostgreSQL-Struktur, die es vor dieser Migration nicht gab. Die Fabrik
``get_workspace_repository`` liefert deshalb immer den Postgres-Adapter und
scheitert nur, wenn ``Config.DATABASE_URL`` fehlt.

``get``/``get_by_slug``/``membership`` geben ``None`` zurueck, wenn es die
Zeile nicht gibt — dieselbe Semantik wie bei den uebrigen Ports. ``create``
wirft ``WorkspaceSlugTaken`` bei einem doppelten Slug (der Adapter definiert
die konkrete Ausnahme). ``add_member`` legt eine Mitgliedschaft an oder
aktualisiert ihre Rolle, wenn sie schon existiert. ``remove_member`` gibt
zurueck, ob eine Zeile da war.
"""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable
from uuid import UUID

from ..config import Config
from ..contracts.workspace_contract import Workspace, WorkspaceMembership, WorkspaceRole


class WorkspaceBackendUnavailable(RuntimeError):
    """``Config.DATABASE_URL`` ist nicht gesetzt.

    Workspaces haben keinen Dateiadapter; ohne eine Datenbankverbindung gibt
    es keine Ablage, ueber die dieser Port bedient werden koennte.
    """


@runtime_checkable
class WorkspaceRepository(Protocol):
    """Lesen und Schreiben von Workspaces und ihren Mitgliedschaften."""

    def get(self, workspace_id: UUID) -> Optional[Workspace]:
        """Ein Workspace oder ``None``, wenn es die ID nicht gibt."""
        ...

    def get_by_slug(self, slug: str) -> Optional[Workspace]:
        """Ein Workspace oder ``None``, wenn der Slug nicht vergeben ist."""
        ...

    def create(self, name: str, slug: str) -> Workspace:
        """Legt einen Workspace an. Wirft ``WorkspaceSlugTaken`` bei einem
        bereits vergebenen Slug."""
        ...

    def list_for_user(self, user_id: UUID) -> List[Workspace]:
        """Alle Workspaces, in denen der Nutzer Mitglied ist."""
        ...

    def membership(
        self, workspace_id: UUID, user_id: UUID
    ) -> Optional[WorkspaceMembership]:
        """Die Mitgliedschaft des Nutzers in diesem Workspace, oder ``None``."""
        ...

    def list_members(self, workspace_id: UUID) -> List[WorkspaceMembership]:
        """Alle Mitgliedschaften eines Workspace."""
        ...

    def user_exists(self, user_id: UUID) -> Optional[bool]:
        """Ob ``user_id`` ein Supabase-Nutzer ist; ``None`` ohne ``auth``-Schema."""
        ...

    def add_member(
        self,
        workspace_id: UUID,
        user_id: UUID,
        role: WorkspaceRole,
        *,
        keep_owner: bool = False,
    ) -> WorkspaceMembership:
        """Legt die Mitgliedschaft an oder aktualisiert ihre Rolle, wenn sie
        bereits existiert. ``keep_owner=True`` verweigert das Herabstufen des
        letzten Owners (``LastOwnerError``)."""
        ...

    def remove_member(
        self, workspace_id: UUID, user_id: UUID, *, keep_owner: bool = False
    ) -> bool:
        """``True``, wenn eine Mitgliedschaft entfernt wurde.
        ``keep_owner=True`` verweigert das Entfernen des letzten Owners."""
        ...


def get_workspace_repository() -> WorkspaceRepository:
    """Die einzige Stelle, an der ein Consumer an ein Workspace-Repository
    kommt. Der Adapter-Import steht in der Funktion, damit ein Modul, das nur
    den Port braucht, SQLAlchemy nicht mitlaedt."""
    if not Config.DATABASE_URL:
        raise WorkspaceBackendUnavailable(
            'Workspaces brauchen DATABASE_URL '
            '(postgresql+psycopg://user:password@host:5432/dbname)'
        )
    from ..infrastructure.postgres.repositories import PostgresWorkspaceRepository

    return PostgresWorkspaceRepository()


__all__ = [
    'WorkspaceBackendUnavailable',
    'WorkspaceRepository',
    'get_workspace_repository',
]
