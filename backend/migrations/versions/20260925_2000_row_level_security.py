"""row level security

Row Level Security für alle workspace-gebundenen Tabellen (ADR-0018, Plan §17,
Issue #1615). Die zweite Schranke hinter den Filtern der Adapter (#1614).

``ENABLE`` und ``FORCE``: ``FORCE`` bindet auch den Tabellen-Owner. Sichtbar
ist eine Zeile, wenn

* die Transaktion im Workspace der Zeile läuft
  (``agora.workspace_id``, gesetzt von ``Database.session()`` aus dem
  Principal), oder
* sie im System-Kontext läuft (``agora.system = 'on'``: Hintergrundarbeit,
  Authentifizierung selbst, Migrationen).

Beide Werte setzt die App je Transaktion mit ``set_config(..., true)``.
Superuser und Rollen mit ``BYPASSRLS`` umgehen RLS immer; das Start-Gate
verweigert deshalb im Tenant-Modus eine solche Laufzeitrolle.

Für die Supabase-Rolle ``authenticated`` (Realtime, #1618) gibt es nur
``SELECT``, gefiltert über ``auth.uid()`` und die Mitgliedschaft — angelegt
nur, wenn Schema ``auth`` und Rolle ``authenticated`` existieren. In der CI mit
reinem PostgreSQL ist dieser Teil ein No-op.

Revision ID: e746a558dce5
Revises: 14d60476b8ce
Create Date: 2026-09-25 20:00:00+02:00

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = 'e746a558dce5'
down_revision: str | None = '14d60476b8ce'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Tabellen mit ``workspace_id``.
SCOPED_TABLES = ('projects', 'simulations', 'runs', 'reports')

#: Gemeinsame Bedingung. ``NULLIF`` macht einen ungesetzten Wert zu NULL statt
#: zu einem Cast-Fehler; NULL vergleicht nie gleich.
_SYSTEM = "current_setting('agora.system', true) = 'on'"
_WORKSPACE = "NULLIF(current_setting('agora.workspace_id', true), '')::uuid"
_ROW_VISIBLE = f'({_SYSTEM} OR workspace_id = {_WORKSPACE})'

#: Alle Anweisungen sind feste Texte; keine Eingabe fließt ein.
_POLICY_NAME = 'agora_workspace_isolation'


def _enable(table: str, condition: str) -> None:
    op.execute(f'ALTER TABLE agora.{table} ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE agora.{table} FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY {_POLICY_NAME} ON agora.{table} '
        f'USING {condition} WITH CHECK {condition}'
    )


def _disable(table: str) -> None:
    op.execute(f'DROP POLICY IF EXISTS {_POLICY_NAME} ON agora.{table}')
    op.execute(f'ALTER TABLE agora.{table} NO FORCE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE agora.{table} DISABLE ROW LEVEL SECURITY')


_AUTHENTICATED_GRANTS = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'auth')
     AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    GRANT USAGE ON SCHEMA agora TO authenticated;
    GRANT SELECT ON agora.workspace_members, agora.projects, agora.simulations,
                    agora.runs, agora.reports TO authenticated;
    EXECUTE 'CREATE POLICY agora_members_self ON agora.workspace_members '
            'FOR SELECT TO authenticated USING (user_id = auth.uid())';
    EXECUTE 'CREATE POLICY agora_member_read ON agora.projects FOR SELECT TO authenticated '
            'USING (workspace_id IN (SELECT workspace_id FROM agora.workspace_members '
            'WHERE user_id = auth.uid()))';
    EXECUTE 'CREATE POLICY agora_member_read ON agora.simulations FOR SELECT TO authenticated '
            'USING (workspace_id IN (SELECT workspace_id FROM agora.workspace_members '
            'WHERE user_id = auth.uid()))';
    EXECUTE 'CREATE POLICY agora_member_read ON agora.runs FOR SELECT TO authenticated '
            'USING (workspace_id IN (SELECT workspace_id FROM agora.workspace_members '
            'WHERE user_id = auth.uid()))';
    EXECUTE 'CREATE POLICY agora_member_read ON agora.reports FOR SELECT TO authenticated '
            'USING (workspace_id IN (SELECT workspace_id FROM agora.workspace_members '
            'WHERE user_id = auth.uid()))';
  END IF;
END
$$;
"""

_AUTHENTICATED_REVOKE = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    DROP POLICY IF EXISTS agora_members_self ON agora.workspace_members;
    DROP POLICY IF EXISTS agora_member_read ON agora.projects;
    DROP POLICY IF EXISTS agora_member_read ON agora.simulations;
    DROP POLICY IF EXISTS agora_member_read ON agora.runs;
    DROP POLICY IF EXISTS agora_member_read ON agora.reports;
    REVOKE SELECT ON agora.workspace_members, agora.projects, agora.simulations,
                     agora.runs, agora.reports FROM authenticated;
    REVOKE USAGE ON SCHEMA agora FROM authenticated;
  END IF;
END
$$;
"""


def upgrade() -> None:
    for table in SCOPED_TABLES:
        _enable(table, _ROW_VISIBLE)
    # Workspaces: sichtbar ist der eigene; Mitgliedschaften ebenso. Die
    # Mitgliedschaftsprüfung beim Anmelden läuft im System-Kontext, weil es
    # dann noch keinen Principal gibt.
    _enable('workspaces', f'({_SYSTEM} OR id = {_WORKSPACE})')
    _enable('workspace_members', _ROW_VISIBLE)
    op.execute(_AUTHENTICATED_GRANTS)


def downgrade() -> None:
    op.execute(_AUTHENTICATED_REVOKE)
    for table in ('workspace_members', 'workspaces', *reversed(SCOPED_TABLES)):
        _disable(table)
