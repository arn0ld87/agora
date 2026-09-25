"""Start-Gate für die Laufzeitrolle unter Row Level Security (ADR-0018, #1615).

RLS schützt nur, wenn die Rolle der App ihm unterliegt. Ein Superuser, eine
Rolle mit ``BYPASSRLS`` und — ohne ``FORCE`` — der Tabellen-Owner umgehen jede
Policy. ``FORCE`` ist gesetzt, trotzdem gilt die Regel aus Plan §17: die
Laufzeitrolle besitzt keine Tabelle. Migrationen laufen über
``AGORA_MIGRATION_DATABASE_URL`` mit der Owner-Rolle.

Im Tenant-Modus (Supabase-JWT aktiv) bricht der Start ab, wenn die Rolle eine
dieser Eigenschaften hat. Einmandantig ist das nur ein Hinweis im Log — dort
gibt es keinen zweiten Workspace, den RLS trennen müsste.

Die Meldung nennt nur die verletzte Eigenschaft, nie Host, Rolle oder
Passwort aus ``DATABASE_URL``.
"""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from .engine import normalize_database_url

_ROLE_SQL = text(
    """
    SELECT r.rolsuper,
           r.rolbypassrls,
           EXISTS (
             SELECT 1 FROM pg_tables
             WHERE schemaname = 'agora' AND tableowner = current_user
           ) AS owns_tables
    FROM pg_roles r
    WHERE r.rolname = current_user
    """
)


class RlsRoleError(RuntimeError):
    """Die Laufzeitrolle würde Row Level Security umgehen."""


def rls_role_violations(database_url: str) -> list[str]:
    """Verletzte Eigenschaften der Rolle hinter ``database_url``."""
    engine = create_engine(
        normalize_database_url(database_url),
        poolclass=NullPool,
        connect_args={'connect_timeout': 5},
    )
    try:
        with engine.connect() as connection:
            row = connection.execute(_ROLE_SQL).one()
    finally:
        engine.dispose()
    violations: list[str] = []
    if row.rolsuper:
        violations.append('superuser')
    if row.rolbypassrls:
        violations.append('BYPASSRLS')
    if row.owns_tables:
        violations.append('owner of agora tables')
    return violations


def verify_rls_role(database_url: str, *, tenant_mode: bool) -> list[str]:
    """Wirft :class:`RlsRoleError` im Tenant-Modus, sonst nur Rückgabe."""
    violations = rls_role_violations(database_url)
    if violations and tenant_mode:
        raise RlsRoleError(
            'runtime database role bypasses row level security ('
            + ', '.join(violations)
            + ') — use a restricted role in DATABASE_URL and run migrations '
            'via AGORA_MIGRATION_DATABASE_URL (docs/runbooks/rls-rollen.md)'
        )
    return violations
