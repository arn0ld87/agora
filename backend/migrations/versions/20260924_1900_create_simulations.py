"""create simulations

Legt die Tabelle für Simulationsmetadaten an (docs/plans/supabase.md §11, PR 7).

Derselbe Schnitt wie bei ``agora.projects``: Kernspalten für das, wonach
gefiltert und verknüpft wird, ``payload`` für den Rest. Kein ``workspace_id``.

``project_id`` verweist auf ``agora.projects(id)``, ist nullable (der Vertrag
kennt ``''`` als "kein Projekt") und ``ON DELETE SET NULL``, weil
``ProjectManager.delete_project`` erst die Artefakte und dann die Zeile
entfernt. Begründung im Modell-Docstring.

Revision ID: c4e8a1d93b56
Revises: 7a3c1e84f209
Create Date: 2026-09-24 19:00:00+02:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c4e8a1d93b56'
down_revision: str | None = '7a3c1e84f209'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = 'agora'
TABLE_NAME = 'simulations'
PROJECT_INDEX = 'ix_simulations_project_id'


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('project_id', sa.Text(), nullable=True),
        sa.Column('graph_id', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('source_simulation_id', sa.Text(), nullable=True),
        sa.Column('root_simulation_id', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=False),
        sa.Column(
            'payload',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        # ``op.f()`` markiert die Namen als final, sonst präfixiert die
        # Naming-Convention aus ``models/base.py`` sie ein zweites Mal.
        sa.CheckConstraint(
            'char_length(id) > 0',
            name=op.f('ck_simulations_id_not_empty'),
        ),
        sa.ForeignKeyConstraint(
            ['project_id'],
            [f'{SCHEMA_NAME}.projects.id'],
            name=op.f('fk_simulations_project_id_projects'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name='pk_simulations'),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        PROJECT_INDEX, TABLE_NAME, ['project_id'], schema=SCHEMA_NAME
    )


def downgrade() -> None:
    op.drop_index(PROJECT_INDEX, table_name=TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_table(TABLE_NAME, schema=SCHEMA_NAME)
