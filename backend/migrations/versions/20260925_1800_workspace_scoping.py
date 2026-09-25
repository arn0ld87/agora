"""workspace scoping

Bindet Projekte, Simulationen, Runs und Reports an einen Workspace
(ADR-0018, Issue #1614).

Drei Schritte je Tabelle, damit ein vorhandener Bestand — auch der
Produktivbestand nach dem Cutover #1592 — ohne Ausfall mitgeht:

1. ``workspace_id`` als nullable Spalte anlegen,
2. jede Zeile dem Default-Workspace zuordnen,
3. ``NOT NULL`` und den Fremdschlüssel auf ``agora.workspaces`` setzen.

Danach werden die Verweise zwischen den Tabellen zusammengesetzt:
``(project_id, workspace_id)`` und ``(simulation_id, workspace_id)`` zeigen auf
``UNIQUE (id, workspace_id)`` des Elternteils. Ein Verweis kann damit nie in
einen anderen Workspace zeigen (Plan §18). ``ON DELETE SET NULL (<spalte>)``
(PostgreSQL ≥ 15) löst beim Löschen des Elternteils nur den Verweis, wie
bisher; ``workspace_id`` bleibt stehen.

LLM-Profile bleiben prozessweit und bekommen keine ``workspace_id`` — sie sind
Betreiber-Einstellungen wie ``/api/settings`` (ADR-0018, Konsequenzen).

Revision ID: 14d60476b8ce
Revises: 5c2913c7ba4f
Create Date: 2026-09-25 18:00:00+02:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '14d60476b8ce'
down_revision: str | None = '5c2913c7ba4f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = 'agora'
# Siehe ``DEFAULT_WORKSPACE_ID`` in ``app/contracts/workspace_contract.py``.
DEFAULT_WORKSPACE_ID = '00000000-0000-0000-0000-000000000001'
TABLES = ('projects', 'simulations', 'runs', 'reports')

#: (Tabelle, Verweisspalte, Elterntabelle) — Reihenfolge der alten Verweise.
REFERENCES = (
    ('simulations', 'project_id', 'projects'),
    ('runs', 'simulation_id', 'simulations'),
    ('reports', 'simulation_id', 'simulations'),
)


def _fk_name(table: str, column: str, parent: str) -> str:
    # Dieselbe Naming-Convention wie ``models/base.py``: der zusammengesetzte
    # Fremdschlüssel trägt den Namen des alten, weil seine erste Spalte gleich
    # bleibt. Die Fehlerbehandlung der Adapter erkennt ihn daran.
    return f'fk_{table}_{column}_{parent}'


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=True),
            schema=SCHEMA,
        )
        rows = sa.table(
            table,
            sa.column('workspace_id', postgresql.UUID(as_uuid=False)),
            schema=SCHEMA,
        )
        op.execute(rows.update().values(workspace_id=DEFAULT_WORKSPACE_ID))
        op.alter_column(table, 'workspace_id', nullable=False, schema=SCHEMA)
        op.create_foreign_key(
            op.f(f'fk_{table}_workspace_id_workspaces'),
            table,
            'workspaces',
            ['workspace_id'],
            ['id'],
            source_schema=SCHEMA,
            referent_schema=SCHEMA,
        )
        op.create_index(
            op.f(f'ix_{table}_workspace_id'), table, ['workspace_id'], schema=SCHEMA
        )

    for parent in ('projects', 'simulations'):
        op.create_unique_constraint(
            op.f(f'uq_{parent}_id'), parent, ['id', 'workspace_id'], schema=SCHEMA
        )

    for table, column, parent in REFERENCES:
        name = _fk_name(table, column, parent)
        op.drop_constraint(op.f(name), table, type_='foreignkey', schema=SCHEMA)
        op.create_foreign_key(
            op.f(name),
            table,
            parent,
            [column, 'workspace_id'],
            ['id', 'workspace_id'],
            source_schema=SCHEMA,
            referent_schema=SCHEMA,
            ondelete=f'SET NULL ({column})',
        )


def downgrade() -> None:
    for table, column, parent in reversed(REFERENCES):
        name = _fk_name(table, column, parent)
        op.drop_constraint(op.f(name), table, type_='foreignkey', schema=SCHEMA)
        op.create_foreign_key(
            op.f(name),
            table,
            parent,
            [column],
            ['id'],
            source_schema=SCHEMA,
            referent_schema=SCHEMA,
            ondelete='SET NULL',
        )

    for parent in ('simulations', 'projects'):
        op.drop_constraint(op.f(f'uq_{parent}_id'), parent, type_='unique', schema=SCHEMA)

    for table in reversed(TABLES):
        op.drop_index(op.f(f'ix_{table}_workspace_id'), table_name=table, schema=SCHEMA)
        op.drop_constraint(
            op.f(f'fk_{table}_workspace_id_workspaces'),
            table,
            type_='foreignkey',
            schema=SCHEMA,
        )
        op.drop_column(table, 'workspace_id', schema=SCHEMA)
