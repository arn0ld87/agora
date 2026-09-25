"""realtime publication

Nimmt die Listen-Tabellen in die Publication ``supabase_realtime`` auf
(ADR-0018, Plan §23, Issue #1618). Supabase Realtime liest daraus
``postgres_changes`` und prüft je Abonnent die RLS-Policy
``agora_member_read`` der Rolle ``authenticated`` (#1615): ein Browser sieht
nur Änderungen aus seinen Workspaces.

Nur ``INSERT`` und ``UPDATE``: Für ``DELETE`` und ``TRUNCATE`` kann Realtime
keine RLS prüfen und schickt das Ereignis mit Primärschlüssel an jeden
Abonnenten der Tabelle, auch aus fremden Workspaces. Gelöschte Zeilen
verschwinden deshalb beim nächsten regulären Nachladen aus der Liste.

Das Frontend nimmt ein Ereignis nur als Signal zum Nachladen über die
Flask-API; der Payload ist keine Datenquelle.

Ohne Publication (reines PostgreSQL, CI) ist die Migration ein No-op. Eine
Publication ``FOR ALL TABLES`` bleibt unverändert.

Revision ID: dc4e84e7c000
Revises: e746a558dce5
Create Date: 2026-09-26 09:00:00+02:00

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = 'dc4e84e7c000'
down_revision: str | None = 'e746a558dce5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Statisches SQL; die Tabellennamen gehen über ``format('%I')`` in die DDL.
_UPGRADE = """
DO $$
DECLARE
  t text;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_publication
             WHERE pubname = 'supabase_realtime' AND NOT puballtables) THEN
    FOREACH t IN ARRAY ARRAY['projects', 'simulations', 'runs', 'reports'] LOOP
      IF NOT EXISTS (SELECT 1 FROM pg_publication_tables
                     WHERE pubname = 'supabase_realtime'
                       AND schemaname = 'agora' AND tablename = t) THEN
        EXECUTE format('ALTER PUBLICATION supabase_realtime ADD TABLE agora.%I', t);
      END IF;
    END LOOP;
    ALTER PUBLICATION supabase_realtime SET (publish = 'insert, update');
  END IF;
END
$$;
"""

_DOWNGRADE = """
DO $$
DECLARE
  t text;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_publication
             WHERE pubname = 'supabase_realtime' AND NOT puballtables) THEN
    FOREACH t IN ARRAY ARRAY['projects', 'simulations', 'runs', 'reports'] LOOP
      IF EXISTS (SELECT 1 FROM pg_publication_tables
                 WHERE pubname = 'supabase_realtime'
                   AND schemaname = 'agora' AND tablename = t) THEN
        EXECUTE format('ALTER PUBLICATION supabase_realtime DROP TABLE agora.%I', t);
      END IF;
    END LOOP;
    -- Supabase legt die Publication mit allen Operationen an.
    ALTER PUBLICATION supabase_realtime SET (publish = 'insert, update, delete, truncate');
  END IF;
END
$$;
"""


def upgrade() -> None:
    op.execute(_UPGRADE)


def downgrade() -> None:
    op.execute(_DOWNGRADE)
