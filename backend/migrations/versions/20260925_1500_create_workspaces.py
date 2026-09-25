"""create workspaces

Legt ``agora.workspaces`` und ``agora.workspace_members`` an (Issue #1612,
docs/plans/supabase.md PR 5) und fügt den Default-Workspace ein
(``00000000-0000-0000-0000-000000000001``, Slug ``default``), damit ein
frischer Bestand einen Workspace zum Verweisen hat, bevor irgendetwas
umgeschaltet wird.

``agora.workspace_members.user_id`` trägt bewusst **keinen** Fremdschlüssel
auf ``auth.users`` — Begründung im Modell-Docstring
(``app/infrastructure/postgres/models/workspace.py``): CI und lokale
Testläufe laufen gegen reines PostgreSQL ohne das Supabase-``auth``-Schema.

Diese Migration importiert keinen App-Code; die Default-ID steht hier als
Literal und ist mit ``DEFAULT_WORKSPACE_ID`` in ``models/workspace.py``
identisch zu halten.

Revision ID: 5c2913c7ba4f
Revises: 8d6e0b3c2f15
Create Date: 2026-09-25 15:00:00+02:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '5c2913c7ba4f'
down_revision: str | None = '8d6e0b3c2f15'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = 'agora'
WORKSPACES_TABLE = 'workspaces'
MEMBERS_TABLE = 'workspace_members'
MEMBERS_USER_INDEX = 'ix_workspace_members_user_id'

# Siehe ``DEFAULT_WORKSPACE_ID`` in ``app/contracts/workspace_contract.py``.
DEFAULT_WORKSPACE_ID = '00000000-0000-0000-0000-000000000001'


def upgrade() -> None:
    op.create_table(
        WORKSPACES_TABLE,
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('slug', sa.Text(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.CheckConstraint(
            'char_length(name) > 0',
            name=op.f('ck_workspaces_name_not_empty'),
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9][a-z0-9-]{0,62}$'",
            name=op.f('ck_workspaces_slug_format'),
        ),
        sa.PrimaryKeyConstraint('id', name='pk_workspaces'),
        sa.UniqueConstraint('slug', name=op.f('uq_workspaces_slug')),
        schema=SCHEMA_NAME,
    )
    op.create_table(
        MEMBERS_TABLE,
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'member', 'viewer')",
            name=op.f('ck_workspace_members_role_valid'),
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'],
            [f'{SCHEMA_NAME}.workspaces.id'],
            name=op.f('fk_workspace_members_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint(
            'workspace_id', 'user_id', name='pk_workspace_members'
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        MEMBERS_USER_INDEX, MEMBERS_TABLE, ['user_id'], schema=SCHEMA_NAME
    )

    # ``op.bulk_insert`` statt roher SQL-Zeichenkette: keine Interpolation von
    # Tabellen-/Spaltennamen, die ein Linter als Injektionsrisiko lesen könnte.
    workspaces_table = sa.table(
        WORKSPACES_TABLE,
        sa.column('id', postgresql.UUID(as_uuid=False)),
        sa.column('name', sa.Text()),
        sa.column('slug', sa.Text()),
        schema=SCHEMA_NAME,
    )
    op.bulk_insert(
        workspaces_table,
        [{'id': DEFAULT_WORKSPACE_ID, 'name': 'Standard', 'slug': 'default'}],
    )


def downgrade() -> None:
    op.drop_index(MEMBERS_USER_INDEX, table_name=MEMBERS_TABLE, schema=SCHEMA_NAME)
    op.drop_table(MEMBERS_TABLE, schema=SCHEMA_NAME)
    op.drop_table(WORKSPACES_TABLE, schema=SCHEMA_NAME)
