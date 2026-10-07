"""create persona sets

Legt ``agora.persona_sets`` an (Issue #1807, Etappe 7: Personasätze).

Derselbe Schnitt wie bei ``agora.simulations``: Kernspalten für das, wonach
sortiert und gesperrt wird, ``payload`` für den Rest des Vertrags
(``app/contracts/persona_set_contract.py``). ``graph_id`` und ``project_id``
sind Verweise ohne Fremdschlüssel; der Satz gehört der Bibliothek.

Die Tabelle ist neu und trägt ``workspace_id`` von Anfang an ``NOT NULL``
(ADR-0018, #1614): es gibt keinen Bestand, der erst dem Default-Workspace
zugeordnet werden müsste. Dazu ``UNIQUE (id, workspace_id)`` wie bei den
übrigen Tabellen.

Row Level Security wie in ``e746a558dce5`` (#1615): ``ENABLE`` und ``FORCE``,
Policy ``agora_workspace_isolation`` mit derselben Bedingung (eigener
Workspace oder System-Kontext). Die Lesepolitik für die Supabase-Rolle
``authenticated`` (Realtime) und die Aufnahme in die Publication
``supabase_realtime`` gibt es für diese Tabelle bewusst nicht: Personasätze
laufen ausschließlich über die Flask-API.

Der Rückweg (``downgrade``) entfernt die Tabelle samt Policy und **allen
gespeicherten Personasätzen**. Die Laufdaten (Simulationen) bleiben, denn ein
Lauf trägt eine Kopie der Personas.

Revision ID: 3b7f9d21a8c4
Revises: dc4e84e7c000
Create Date: 2026-10-07 12:00:00+02:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '3b7f9d21a8c4'
down_revision: str | None = 'dc4e84e7c000'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = 'agora'
TABLE_NAME = 'persona_sets'

#: Gleiche Bedingung wie in ``20260925_2000_row_level_security``. ``NULLIF``
#: macht einen ungesetzten Wert zu NULL statt zu einem Cast-Fehler.
_SYSTEM = "current_setting('agora.system', true) = 'on'"
_WORKSPACE = "NULLIF(current_setting('agora.workspace_id', true), '')::uuid"
_ROW_VISIBLE = f'({_SYSTEM} OR workspace_id = {_WORKSPACE})'
_POLICY_NAME = 'agora_workspace_isolation'


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('graph_id', sa.Text(), nullable=True),
        sa.Column('project_id', sa.Text(), nullable=True),
        sa.Column('locked_at', sa.Text(), nullable=True),
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
            'char_length(id) > 0', name=op.f('ck_persona_sets_id_not_empty')
        ),
        sa.CheckConstraint(
            'char_length(name) > 0', name=op.f('ck_persona_sets_name_not_empty')
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'],
            [f'{SCHEMA_NAME}.workspaces.id'],
            name=op.f('fk_persona_sets_workspace_id_workspaces'),
        ),
        sa.PrimaryKeyConstraint('id', name='pk_persona_sets'),
        sa.UniqueConstraint('id', 'workspace_id', name=op.f('uq_persona_sets_id')),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        op.f('ix_persona_sets_workspace_id'),
        TABLE_NAME,
        ['workspace_id'],
        schema=SCHEMA_NAME,
    )

    # Alle Anweisungen sind feste Texte; keine Eingabe fließt ein.
    op.execute(f'ALTER TABLE {SCHEMA_NAME}.{TABLE_NAME} ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE {SCHEMA_NAME}.{TABLE_NAME} FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY {_POLICY_NAME} ON {SCHEMA_NAME}.{TABLE_NAME} '
        f'USING {_ROW_VISIBLE} WITH CHECK {_ROW_VISIBLE}'
    )


def downgrade() -> None:
    op.execute(f'DROP POLICY IF EXISTS {_POLICY_NAME} ON {SCHEMA_NAME}.{TABLE_NAME}')
    op.drop_index(
        op.f('ix_persona_sets_workspace_id'),
        table_name=TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(TABLE_NAME, schema=SCHEMA_NAME)
