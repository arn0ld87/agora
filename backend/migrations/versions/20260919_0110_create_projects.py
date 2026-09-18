"""create projects

Legt die Tabelle für Projekt-Metadaten an (docs/plans/supabase.md §11, PR 6).

Der Spaltenschnitt ist die am Gate getroffene Entscheidung: Kernspalten für
das, wonach abgefragt und sortiert wird, ``payload`` für den Rest. Kein
``workspace_id`` — Multi-User ist eine eigene, freizugebende Phase.

``id`` bleibt ``text``, weil die Kennung zugleich der Verzeichnisname unter
``uploads/projects/`` ist. ``created_at``/``updated_at`` bleiben ``text``, weil
der Vertrag ISO-Zeichenketten führt und ein Umweg über ``timestamptz`` beim
Zurücklesen eine andere Zeichenkette ergäbe. Begründung im Modell-Docstring.

Revision ID: 7a3c1e84f209
Revises: b5d2c0a41f7e
Create Date: 2026-09-19 01:10:00+02:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '7a3c1e84f209'
down_revision: str | None = 'b5d2c0a41f7e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = 'agora'
TABLE_NAME = 'projects'
INDEX_NAME = 'ix_projects_created_at'

#: Muss mit ``PROJECT_STATUS_VALUES`` im Modell übereinstimmen. Der
#: Integrationstest prüft genau das gegeneinander, damit die beiden Listen
#: nicht auseinanderlaufen.
STATUS_VALUES = (
    'created',
    'ontology_generated',
    'graph_building',
    'graph_completed',
    'graph_incomplete',
    'failed',
)

_STATUS_IN_LIST = ', '.join(f"'{value}'" for value in STATUS_VALUES)


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('graph_id', sa.Text(), nullable=True),
        sa.Column('llm_profile_id', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=False),
        sa.Column(
            'payload',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        # ``op.f()`` markiert die Namen als final. Ohne das präfixiert die
        # Naming-Convention aus ``models/base.py`` sie ein zweites Mal, und in
        # der Datenbank stünde ``ck_projects_ck_projects_…`` — genau der
        # Fehler, der in PR 3 entstanden ist.
        sa.CheckConstraint(
            'char_length(id) > 0',
            name=op.f('ck_projects_id_not_empty'),
        ),
        sa.CheckConstraint(
            f'status IN ({_STATUS_IN_LIST})',
            name=op.f('ck_projects_status_known'),
        ),
        sa.PrimaryKeyConstraint('id', name='pk_projects'),
        schema=SCHEMA_NAME,
    )
    # Absteigend, weil die Projektliste das Neueste oben zeigt.
    op.create_index(
        INDEX_NAME,
        TABLE_NAME,
        [sa.text('created_at DESC')],
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name=TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_table(TABLE_NAME, schema=SCHEMA_NAME)
