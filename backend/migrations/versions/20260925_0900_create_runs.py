"""create runs

Legt die Tabelle für Run-Manifeste an (docs/plans/supabase.md §11, PR 8).

``payload`` ist das vollständige Manifest, die übrigen Spalten sind daraus
abgeleitete Projektionen für Sortierung, Filter und den Fremdschlüssel —
Begründung im Modell-Docstring (``RunRecord`` unterscheidet "fehlt" von
"``null``"). Kein ``workspace_id``.

``simulation_id`` verweist auf ``agora.simulations(id)``, ist nullable
(Graph-Build-Runs haben keine Simulation) und ``ON DELETE SET NULL``, damit
die Run-Historie eine gelöschte Simulation überlebt.

Revision ID: 3f9b2d7e6a41
Revises: c4e8a1d93b56
Create Date: 2026-09-25 09:00:00+02:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '3f9b2d7e6a41'
down_revision: str | None = 'c4e8a1d93b56'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = 'agora'
TABLE_NAME = 'runs'
SIMULATION_INDEX = 'ix_runs_simulation_id'


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('run_type', sa.Text(), nullable=True),
        sa.Column('entity_id', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('simulation_id', sa.Text(), nullable=True),
        sa.Column('started_at', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.Text(), nullable=True),
        sa.Column('completed_at', sa.Text(), nullable=True),
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
            name=op.f('ck_runs_id_not_empty'),
        ),
        sa.ForeignKeyConstraint(
            ['simulation_id'],
            [f'{SCHEMA_NAME}.simulations.id'],
            name=op.f('fk_runs_simulation_id_simulations'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name='pk_runs'),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        SIMULATION_INDEX, TABLE_NAME, ['simulation_id'], schema=SCHEMA_NAME
    )


def downgrade() -> None:
    op.drop_index(SIMULATION_INDEX, table_name=TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_table(TABLE_NAME, schema=SCHEMA_NAME)
