"""create agora schema

Legt das Fachschema `agora` an (docs/plans/supabase.md §9).

Die Tabellen entstehen erst in Phase 3. Diese Migration steht trotzdem schon
hier, aus zwei Gruenden: sie macht das Alembic-Setup nachweisbar lauffaehig
statt nur vorhanden, und jede Phase-3-Migration setzt das Schema voraus.

`public` bleibt bewusst leer. Es ist das Schema, das PostgREST ueber die
Supabase-API nach aussen reicht; Fachtabellen gehoeren nicht versehentlich
dorthin.

Revision ID: e4d811c90e00
Revises:
Create Date: 2026-09-16 23:39:01.032081+00:00

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = 'e4d811c90e00'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = 'agora'


def upgrade() -> None:
    # Ohne `IF NOT EXISTS`, mit Absicht. Ab hier gilt: das Schema wird
    # ausschliesslich ueber versionierte Migrationen geaendert (§8). Existiert
    # `agora` schon, hat es jemand von Hand angelegt — dann soll diese
    # Migration scheitern und nicht so tun, als haette sie es getan.
    op.execute(f'CREATE SCHEMA {SCHEMA_NAME}')

    # Rechte fuer die Supabase-Rollen (anon, authenticated, service_role)
    # kommen mit den Tabellen in Phase 3 (§9) und ihren RLS-Policies (§17).
    # Ein leeres Schema hat nichts zu vergeben.


def downgrade() -> None:
    # RESTRICT (der Default) statt CASCADE: ein Rollback darf Tabellen, die
    # spaetere Migrationen angelegt haben, nicht mitnehmen. Liegt noch etwas
    # im Schema, scheitert dieser Schritt laut — und das ist die richtige
    # Antwort, weil erst die Migration dran ist, die den Inhalt angelegt hat.
    op.execute(f'DROP SCHEMA {SCHEMA_NAME}')
