"""Persistenzmodelle für Workspaces und ihre Mitgliedschaften (Issue #1612,
docs/plans/supabase.md PR 5).

Dies ist die erste Multi-User-Tabelle im Fachschema. Sie legt nur die
Struktur — Workspace, Mitgliedschaft, Rolle — an; **umgeschaltet ist damit
nichts**: kein bestehender Store liest oder schreibt hierüber, Simulationen,
Projekte und Reports bleiben ohne ``workspace_id`` (siehe deren
Modul-Docstrings, "Multi-User ist eine eigene, freizugebende Phase").

``agora.workspace_members.user_id`` trägt **keinen** Fremdschlüssel auf
``auth.users``. Supabase legt dieses Schema in Produktion an, aber die
CI-Umgebung und lokale Testläufe (``AGORA_TEST_POSTGRES_URL``) laufen gegen
ein reines PostgreSQL ohne das Supabase-``auth``-Schema — eine Migration mit
einem Fremdschlüssel dorthin würde dort nicht anwenden. Die referenzielle
Integrität zu ``auth.users`` ist deshalb Sache der Anwendungsschicht, bis es
eine eigene Entscheidung dazu gibt.

``DEFAULT_WORKSPACE_ID`` ist die feste UUID des Default-Workspace, den die
Migration einfügt (``00000000-0000-0000-0000-000000000001``). Die Migration
selbst darf dieses Modul nicht importieren (Migrationen sind von Code
unabhängig zu halten) und trägt denselben Literalwert mit einem Verweis
hierher als Kommentar.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ....contracts.workspace_contract import DEFAULT_WORKSPACE_ID as CONTRACT_DEFAULT_WORKSPACE_ID
from .base import AGORA_SCHEMA, Base

#: Feste ID des Default-Workspace, den die Migration
#: ``20260925_1500_create_workspaces`` einfügt. Die Migration hardcodet
#: denselben Literalwert (Migrationen importieren keinen App-Code).
# Kanonisch im Vertrag; hier re-exportiert für bestehende Importe.
DEFAULT_WORKSPACE_ID = CONTRACT_DEFAULT_WORKSPACE_ID

#: Gültige Rollenwerte für ``agora.workspace_members.role``.
WORKSPACE_ROLE_VALUES = frozenset({'owner', 'admin', 'member', 'viewer'})


class WorkspaceModel(Base):
    """Ein Workspace: Name und eindeutiger Slug."""

    __tablename__ = 'workspaces'
    __table_args__ = (
        CheckConstraint(
            'char_length(name) > 0',
            name='name_not_empty',
        ),
        CheckConstraint(
            "slug ~ '^[a-z0-9][a-z0-9-]{0,62}$'",
            name='slug_format',
        ),
        {'schema': AGORA_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class WorkspaceMemberModel(Base):
    """Mitgliedschaft eines Nutzers in einem Workspace mit genau einer Rolle.

    ``user_id`` verweist bewusst auf keine Tabelle — siehe Modul-Docstring.
    """

    __tablename__ = 'workspace_members'
    __table_args__ = (
        PrimaryKeyConstraint('workspace_id', 'user_id', name='pk_workspace_members'),
        CheckConstraint(
            "role IN ('owner', 'admin', 'member', 'viewer')",
            name='role_valid',
        ),
        # ``list_for_user`` ist der häufigste Lesepfad neben dem Primärschlüssel.
        Index('ix_workspace_members_user_id', 'user_id'),
        {'schema': AGORA_SCHEMA},
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f'{AGORA_SCHEMA}.workspaces.id', ondelete='CASCADE'),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
