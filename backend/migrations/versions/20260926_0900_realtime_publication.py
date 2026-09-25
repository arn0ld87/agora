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
Publication ``FOR ALL TABLES`` enthält die Tabellen schon; auch dort gilt
danach nur noch ``INSERT``/``UPDATE``.

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
#: ``public.agora_realtime_baseline`` hält den Vorzustand (``publish`` und
#: schon veröffentlichte Tabellen), damit der Downgrade genau ihn wiederherstellt
#: und keine Einstellung des Betreibers verwirft. Sie liegt außerhalb von
#: ``agora`` und damit außerhalb von ``alembic check``.
_UPGRADE = """
DO $$
DECLARE
  t text;
  ops text[];
BEGIN
  IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
    CREATE TABLE IF NOT EXISTS public.agora_realtime_baseline (
      kind text NOT NULL,
      value text NOT NULL,
      PRIMARY KEY (kind, value)
    );
    IF NOT EXISTS (SELECT 1 FROM public.agora_realtime_baseline) THEN
      SELECT array_remove(ARRAY[
               CASE WHEN pubinsert THEN 'insert' END,
               CASE WHEN pubupdate THEN 'update' END,
               CASE WHEN pubdelete THEN 'delete' END,
               CASE WHEN pubtruncate THEN 'truncate' END], NULL)
        INTO ops FROM pg_publication WHERE pubname = 'supabase_realtime';
      INSERT INTO public.agora_realtime_baseline VALUES ('publish', array_to_string(ops, ', '));
      INSERT INTO public.agora_realtime_baseline
        SELECT 'table', tablename FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime' AND schemaname = 'agora'
          AND tablename = ANY (ARRAY['projects', 'simulations', 'runs', 'reports']);
    END IF;
    -- FOR ALL TABLES enthält die Tabellen schon; ADD TABLE wäre ein Fehler.
    IF NOT (SELECT puballtables FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
      FOREACH t IN ARRAY ARRAY['projects', 'simulations', 'runs', 'reports'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_publication_tables
                       WHERE pubname = 'supabase_realtime'
                         AND schemaname = 'agora' AND tablename = t) THEN
          EXECUTE format('ALTER PUBLICATION supabase_realtime ADD TABLE agora.%I', t);
        END IF;
      END LOOP;
    END IF;
    -- In jedem Fall: DELETE und TRUNCATE prüft Realtime nicht gegen RLS.
    ALTER PUBLICATION supabase_realtime SET (publish = 'insert, update');
  END IF;
END
$$;
"""

_DOWNGRADE = """
DO $$
DECLARE
  t text;
  kept text[] := '{}';
  previous text;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
    IF to_regclass('public.agora_realtime_baseline') IS NOT NULL THEN
      SELECT coalesce(array_agg(value), '{}') INTO kept
        FROM public.agora_realtime_baseline WHERE kind = 'table';
      SELECT value INTO previous
        FROM public.agora_realtime_baseline WHERE kind = 'publish';
    END IF;
    IF NOT (SELECT puballtables FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
      FOREACH t IN ARRAY ARRAY['projects', 'simulations', 'runs', 'reports'] LOOP
        IF NOT (t = ANY (kept)) AND EXISTS (SELECT 1 FROM pg_publication_tables
                   WHERE pubname = 'supabase_realtime'
                     AND schemaname = 'agora' AND tablename = t) THEN
          EXECUTE format('ALTER PUBLICATION supabase_realtime DROP TABLE agora.%I', t);
        END IF;
      END LOOP;
    END IF;
    -- Ohne Vorzustand: Supabase legt die Publication mit allen Operationen an.
    EXECUTE format('ALTER PUBLICATION supabase_realtime SET (publish = %L)',
                   coalesce(previous, 'insert, update, delete, truncate'));
  END IF;
  DROP TABLE IF EXISTS public.agora_realtime_baseline;
END
$$;
"""


def upgrade() -> None:
    op.execute(_UPGRADE)


def downgrade() -> None:
    op.execute(_DOWNGRADE)
