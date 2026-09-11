-- Agora Supabase-Mirror — Schema `agora` (Phase 1)
--
-- Apply auf dem self-hosted Supabase (Postgres-Rolle `postgres` / Studio-SQL):
--   psql "$SUPABASE_DB_URL" -f deploy/supabase/schema.sql
--
-- Vertrag (docs/plans/supabase.md):
-- - Postgres ist NUR Spiegel/Index. Wahrheit: Dateisystem (Run-Manifeste,
--   Report-Metadaten, Dokument-Manifeste) bzw. Neo4j (Graph/Vektoren).
--   Jede Zeile ist via `python -m app.services.supabase_mirror.rebuild`
--   verlustfrei rekonstruierbar.
-- - Quell-Zeitstempel bleiben ISO-Text (naive Europe/Berlin-Strings der
--   Agora-Artefakte). mirrored_at setzt der Mirror selbst (UTC, App-Uhr);
--   der Default now() ist nur Fallback fuer Direkt-Inserts. Eine Uhr fuer
--   Write und Rebuild-Sweep — sonst loescht Uhren-Drift frische Zeilen.
-- - RLS auf jeder Tabelle, deny-by-default: keine Policies fuer
--   anon/authenticated vor Phase 3. Private Schemas sind kein
--   RLS-Ersatz (Defense-in-Depth).
-- - Realtime (Phase 2): nur run_events, INSERT-Broadcast; Sichtbarkeit
--   regelt RLS (fuer anon: keine Zeilen, bis Phase 3 Policies existieren).
-- - Edge Functions, Auth (GoTrue), public-Schema: bewusst ungenutzt.

create schema if not exists agora;

create table if not exists agora.runs (
    run_id             text primary key,
    run_type           text not null,
    entity_id          text not null,
    parent_run_id      text,
    status             text not null,
    progress           integer not null default 0 check (progress between 0 and 100),
    message            text not null default '',
    error              text,
    started_at         text not null,
    updated_at         text not null,
    completed_at       text,
    branch_label       text,
    termination_reason text,
    project_id         text,
    simulation_id      text,
    mirrored_at        timestamptz not null default now()
);

create table if not exists agora.run_events (
    run_id      text not null references agora.runs(run_id) on delete cascade,
    seq         integer not null check (seq >= 0),
    occurred_at text not null,
    event_type  text not null,
    status      text not null,
    progress    integer check (progress between 0 and 100),
    message     text not null default '',
    mirrored_at timestamptz not null default now(),
    primary key (run_id, seq)
);

create index if not exists run_events_run_id_seq_idx
    on agora.run_events (run_id, seq);

create table if not exists agora.report_index (
    report_id         text primary key,
    status            text not null,
    evidence_ok       boolean not null default false,
    evidence_sections integer not null default 0 check (evidence_sections >= 0),
    artifact_path     text not null,
    created_at        text,
    updated_at        text,
    mirrored_at       timestamptz not null default now()
);

create table if not exists agora.documents (
    project_id  text not null,
    document_id text not null,
    filename    text not null,
    size_bytes  bigint check (size_bytes is null or size_bytes >= 0),
    sha256      text,
    ingested_at text,
    mirrored_at timestamptz not null default now(),
    primary key (project_id, document_id)
);

create table if not exists agora.audit_log (
    id          bigint generated always as identity primary key,
    kind        text not null,
    subject_id  text not null,
    details     jsonb not null default '{}'::jsonb,
    created_at  timestamptz not null default now()
);
-- audit_log ist Teil des Phase-1-Vertrags und hat bewusst noch keinen
-- Writer (Phase 3 schreibt hier Token-/Policy-relevante Ereignisse).

create index if not exists runs_project_id_idx on agora.runs (project_id);
create index if not exists runs_simulation_id_idx on agora.runs (simulation_id);
create index if not exists runs_status_idx on agora.runs (status);
create index if not exists documents_project_id_idx on agora.documents (project_id);

-- ---------------------------------------------------------------------------
-- RLS: deny-by-default. Keine Policies fuer anon/authenticated vor Phase 3.
-- service_role umgeht RLS per Definition (bypassrls) — nur das Flask-Backend
-- kennt diesen Key (Env, nie Frontend).
-- ---------------------------------------------------------------------------
alter table agora.runs        enable row level security;
alter table agora.run_events  enable row level security;
alter table agora.report_index enable row level security;
alter table agora.documents   enable row level security;
alter table agora.audit_log   enable row level security;

-- Haerte ueber RLS hinaus: Data-API-Rollen bekommen keinerlei Grants auf
-- das Schema. `agora` ist zwar fuer PostgREST exponiert (siehe unten —
-- sonst koennte der Mirror gar nicht schreiben), aber ohne Grants und mit
-- RLS deny-by-default sehen anon/authenticated dort nichts.
revoke all on schema agora from anon, authenticated;
revoke all on all tables in schema agora from anon, authenticated;

grant usage on schema agora to service_role;
grant all on all tables in schema agora to service_role;

-- ---------------------------------------------------------------------------
-- PostgREST: Schema `agora` exponieren.
--
-- Der Mirror schreibt mit `Content-Profile: agora` und liest den Healthcheck
-- mit `Accept-Profile: agora`. Steht `agora` nicht in `db-schemas`, antwortet
-- PostgREST mit PGRST106 (schema not exposed) und JEDER Upsert scheitert.
--
-- Bevorzugt ueber die Deployment-Config setzen (ueberlebt einen
-- `notify pgrst`-Reload nicht nur, sondern auch Container-Neubauten):
--   docker-compose (supabase/rest):  PGRST_DB_SCHEMAS=public,storage,graphql_public,agora
--
-- Wer die Compose-Datei nicht anfassen kann/will, setzt es hier in der DB.
-- ACHTUNG: Die Rollen-Einstellung ERSETZT die Liste vollstaendig — die
-- bestehenden Supabase-Schemas muessen mit aufgezaehlt werden, sonst bricht
-- die uebrige Data-API. Vorher pruefen:
--   select current_setting('pgrst.db_schemas', true);
--
-- alter role authenticator set pgrst.db_schemas = 'public, storage, graphql_public, agora';
-- notify pgrst, 'reload config';
--
-- Verifikation (muss 200 liefern, nicht PGRST106):
--   curl -sS -o /dev/null -w '%{http_code}\n' \
--     -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
--     -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
--     -H 'Accept-Profile: agora' \
--     "$SUPABASE_URL/rest/v1/runs?select=count&limit=1"
-- Gleichwertig: `python -m app.services.supabase_mirror.rebuild --check`.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- Realtime (Phase 2): NUR run_events veröffentlichen. Aktivieren, sobald
-- Phase 2 (Frontend-Realtime-Subscribe) umgesetzt wird; bis dahin
-- auskommentiert, damit der Broadcast-Kanal keine Oberfläche bietet.
--
-- alter publication supabase_realtime add table agora.run_events;
--
-- Kein Presence, keine *-Replikation, keine auth-Schema-Topics.
-- ---------------------------------------------------------------------------
