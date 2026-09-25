"""create reports

Legt die Tabelle für Report-Metadaten an (docs/plans/supabase.md §11, PR 9).

Derselbe Schnitt wie bei ``agora.runs``: ``payload`` ist der vollständige
Inhalt von ``meta.json``, die übrigen Spalten sind daraus abgeleitete
Projektionen. ``id`` ist der Ablageschlüssel (Ordnername), nicht zwingend die
``report_id`` im Datensatz — Begründung im Modell-Docstring. Kein
``workspace_id``. Report-Inhalte bleiben Dateien.

``simulation_id`` verweist auf ``agora.simulations(id)``, ist nullable und
``ON DELETE SET NULL``, damit ein Report seine Simulation überlebt.

Revision ID: 8d6e0b3c2f15
Revises: 3f9b2d7e6a41
Create Date: 2026-09-25 12:00:00+02:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '8d6e0b3c2f15'
down_revision: str | None = '3f9b2d7e6a41'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = 'agora'
TABLE_NAME = 'reports'
SIMULATION_INDEX = 'ix_reports_simulation_id'


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('report_id', sa.Text(), nullable=False),
        sa.Column('simulation_id', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Text(), nullable=True),
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
            name=op.f('ck_reports_id_not_empty'),
        ),
        sa.ForeignKeyConstraint(
            ['simulation_id'],
            [f'{SCHEMA_NAME}.simulations.id'],
            name=op.f('fk_reports_simulation_id_simulations'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name='pk_reports'),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        SIMULATION_INDEX, TABLE_NAME, ['simulation_id'], schema=SCHEMA_NAME
    )


def downgrade() -> None:
    op.drop_index(SIMULATION_INDEX, table_name=TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_table(TABLE_NAME, schema=SCHEMA_NAME)
