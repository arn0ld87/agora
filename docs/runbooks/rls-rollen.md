# Row Level Security: Rollen einrichten

Seit #1615 stehen alle workspace-gebundenen Tabellen unter `FORCE ROW LEVEL
SECURITY` (ADR-0018, Plan §17). Das schützt nur, wenn die App mit einer Rolle
arbeitet, die RLS nicht umgeht. Dieses Runbook trennt deshalb zwei Rollen:

| Rolle | Variable | Rechte | Wofür |
|---|---|---|---|
| Owner (z. B. `postgres`) | `AGORA_MIGRATION_DATABASE_URL` | besitzt Schema und Tabellen | Alembic, `pg_restore`, Backup |
| `agora_app` | `DATABASE_URL` | nur DML, kein `BYPASSRLS`, kein Owner | die laufende App |

Einmandantig (ohne Supabase-JWT) ist die Trennung empfohlen, aber nicht
erzwungen. Im Tenant-Modus bricht der Start ab, wenn `DATABASE_URL` auf einen
Superuser, eine Rolle mit `BYPASSRLS` oder den Tabellen-Owner zeigt.

## Ablauf

1. Schema auf den Head bringen, als Owner:

   ```bash
   cd backend
   AGORA_MIGRATION_DATABASE_URL='postgresql+psycopg://postgres:<PW>@<host>:5432/postgres' \
     uv run alembic -c migrations/alembic.ini upgrade head
   ```

2. Laufzeitrolle anlegen, als Owner in `psql`:

   ```sql
   CREATE ROLE agora_app LOGIN PASSWORD '<starkes Passwort>' NOSUPERUSER NOBYPASSRLS;
   GRANT USAGE ON SCHEMA agora TO agora_app;
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA agora TO agora_app;
   ALTER DEFAULT PRIVILEGES IN SCHEMA agora
     GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO agora_app;
   -- Das Start-Gate (#1582) liest die Revision.
   GRANT SELECT ON public.alembic_version TO agora_app;
   ```

   `ALTER DEFAULT PRIVILEGES` gilt für Tabellen, die der ausführende Owner künftig anlegt. Laufen Migrationen unter einer anderen Rolle, braucht es `FOR ROLE <owner>`.

3. `.env` setzen und neu starten:

   ```bash
   DATABASE_URL=postgresql+psycopg://agora_app:<PW>@<host>:5432/postgres
   AGORA_MIGRATION_DATABASE_URL=postgresql+psycopg://postgres:<PW>@<host>:5432/postgres
   ```

## Prüfen

```bash
# Rolle umgeht RLS nicht (erwartet: f | f)
psql "$DATABASE_URL_PSQL" -Atc "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
# Ohne Kontext ist nichts sichtbar (erwartet: 0)
psql "$DATABASE_URL_PSQL" -Atc "SELECT count(*) FROM agora.projects"
```

Im Log der App steht beim Start nichts zu „RLS: Laufzeitrolle umgeht Row Level Security“.

## Wie die App den Kontext setzt

`Database.session()` setzt je Transaktion `agora.workspace_id` (aus dem Principal) oder `agora.system = on`. Letzteres gilt für Hintergrundarbeit, Start-Reconciliation, Migrationsskripte und die Mitgliedschaftsprüfung beim Anmelden. `pg_dump` und `pg_restore` laufen mit `--enable-row-security` und `PGOPTIONS='-c agora.system=on'`. Eine Verbindung ohne Kontext sieht keine Zeile (fail-closed).

## Rückweg

`alembic downgrade 14d60476b8ce` (als Owner) entfernt Policies und RLS. Die Laufzeitrolle kann bleiben.
