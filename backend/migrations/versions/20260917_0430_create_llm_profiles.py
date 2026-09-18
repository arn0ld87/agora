"""create llm profiles

Legt das erste fachliche PostgreSQL-Modell für Agora an. Die Tabelle enthält
nur LLM-Profil-Metadaten: Provider-Secrets und vorgezogene Workspace-/Auth-
Abhängigkeiten sind ausdrücklich nicht Teil dieser Revision.

Revision ID: b5d2c0a41f7e
Revises: e4d811c90e00
Create Date: 2026-09-17 04:30:00+02:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b5d2c0a41f7e'
down_revision: str | None = 'e4d811c90e00'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = 'agora'
TABLE_NAME = 'llm_profiles'


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('provider', sa.Text(), nullable=False),
        sa.Column('base_url', sa.Text(), nullable=False),
        sa.Column('model_name', sa.Text(), nullable=False),
        sa.Column(
            'is_default',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
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
            'char_length(name) BETWEEN 1 AND 80',
            name=op.f('ck_llm_profiles_name_length'),
        ),
        sa.CheckConstraint(
            'char_length(provider) > 0',
            name=op.f('ck_llm_profiles_provider_not_empty'),
        ),
        sa.CheckConstraint(
            'char_length(base_url) > 0',
            name=op.f('ck_llm_profiles_base_url_not_empty'),
        ),
        sa.CheckConstraint(
            'char_length(model_name) > 0',
            name=op.f('ck_llm_profiles_model_name_not_empty'),
        ),
        sa.PrimaryKeyConstraint('id', name='pk_llm_profiles'),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        'uq_llm_profiles_single_default',
        TABLE_NAME,
        ['is_default'],
        unique=True,
        schema=SCHEMA_NAME,
        postgresql_where=sa.text('is_default'),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_llm_profiles_single_default',
        table_name=TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(TABLE_NAME, schema=SCHEMA_NAME)
