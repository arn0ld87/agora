# Supabase-Mirror (Phase 0/1)

Self-hosted Supabase als App-Metadaten-Index (`schema agora`). **Postgres ist
Spiegel, nie Wahrheit** — Wahrheit bleibt: Dateisystem (Run-Manifeste,
Report-Metadaten, Dokument-Manifeste), Neo4j (Graph/Vektoren), Ollama
(Inferenz). Kein Auth, keine Edge Functions, kein `public`-Schema.

## Setup (Operator)

1. Schema anlegen (idempotent, re-laufbar):

   ```bash
   psql "$SUPABASE_DB_URL" -f deploy/supabase/schema.sql
   ```

2. Schema `agora` fuer PostgREST exponieren — **sonst scheitert jeder
   Upsert mit PGRST106 (`schema must be one of the following: ...`)**.
   Der Mirror schreibt mit `Content-Profile: agora`, liest mit
   `Accept-Profile: agora`:

   ```text
   # supabase/docker/.env bzw. Service `rest` in docker-compose.yml
   PGRST_DB_SCHEMAS=public,storage,graphql_public,agora
   ```

   Alternativ in der DB (ersetzt die Liste vollstaendig, also die
   bestehenden Schemas mit aufzaehlen — Details und Verifikations-`curl`
   stehen als Kommentar in `schema.sql`):

   ```sql
   alter role authenticator set pgrst.db_schemas = 'public, storage, graphql_public, agora';
   notify pgrst, 'reload config';
   ```

   Grants und RLS bleiben davon unberuehrt: `anon`/`authenticated` haben
   auf `agora` keine Grants und RLS ist deny-by-default — exponiert heisst
   nicht lesbar.

3. Agora-Backend-Env setzen (`.env`, Werte via Vaultwarden — nie im Repo):

   ```text
   SUPABASE_ENABLED=true
   SUPABASE_URL=<interner Kong/REST-Endpoint, z.B. Compose-Service oder Tailscale>
   SUPABASE_SERVICE_ROLE_KEY=<service_role key — NUR Backend-Env, nie Frontend>
   ```

   Ohne `SUPABASE_ENABLED=true` verhält sich Agora exakt wie vorher
   (null Netzwerkaufrufe). `Config.validate()` lehnt `SUPABASE_ENABLED=true`
   ohne URL/Key beim Start ab.

4. Netz: Läuft Supabase auf demselben Docker-Host, das `supabase`-Netz
   ans Agora-Backend hängen (external network) — sonst interne URL über
   Tailscale. Kong-Ports müssen dafür nicht auf dem Host published werden.

5. Healthcheck + Rebuild:

   ```bash
   cd backend
   uv run python -m app.services.supabase_mirror.rebuild --check   # Dry-Run
   uv run python -m app.services.supabase_mirror.rebuild           # Voll-Rebuild
   ```

   `--check` prüft mit `Accept-Profile: agora` gegen eine Mirror-Tabelle:
   Ein 200 beweist Erreichbarkeit *und* korrekte `db-schemas`-Config.

   Der Voll-Rebuild rekonstruiert runs/run_events/report_index/documents
   komplett aus der lokalen Wahrheit und ist der Rollforward nach
   Supabase-Ausfällen oder Schema-Änderungen. Er ist nicht nur additiv:
   Jede geschriebene Zeile trägt den Startstempel des Laufs in
   `mirrored_at`, anschließend löscht ein Sweep alles Ältere — Zeilen
   lokal gelöschter Runs/Reports/Projekte verschwinden damit aus dem
   Spiegel.

## Was gespiegelt wird (Write-Through, best-effort)

| Tabelle | Quelle (Wahrheit) | Hook |
|---|---|---|
| `agora.runs` | `backend/uploads/run_registry/<run_id>.json` | `RunRegistry._write_run` |
| `agora.run_events` | Events im Run-Manifest (append-only, Delta) | `RunRegistry._write_run` |
| `agora.report_index` | `backend/uploads/reports/<id>/meta.json` | `ReportManager.save_report` |
| `agora.documents` | Projekt-Dokument-Manifeste (`extracted_documents.json`) | Upload-Endpoint `api/graph_build.py` |
| `agora.audit_log` | — (bewusst ohne Writer, Phase 3) | — |

Fehler sind nie fatal: Mirror-Ausfälle loggen (`warning`) und ändern das
Pipeline-Verhalten nicht. Der nächste Rebuild schließt Lücken.

## Sicherheit

- `service_role` nur im Backend-Env; Frontend bekommt ihn nie (Phase 2
  nutzt ausschließlich den anon key für Realtime).
- RLS auf jeder Tabelle, deny-by-default; zusätzlich REVOKEd Grants für
  `anon`/`authenticated` auf Schema und Tabellen.
- `run_events` speichert Status-Metriken (max. 1000 Zeichen Message) —
  keine Prompt-/Dokumentinhalte.
- Phase 2 aktiviert die Realtime-Publication für `run_events` (in
  `schema.sql` auskommentiert vorgesehen).

## Explizit NICHT (Auslagerungsmatrix, docs/plans/supabase.md)

Graph/Embeddings (Neo4j), Report-Artefakte (Dateisystem, Evidence-Commit-
Modell), Agent-State (OASIS-Prozess), Logs (Observability-Stack), Secrets
(Fernet-Store/Vaultwarden), Edge Functions, GoTrue-Auth (frühestens Phase 3
bei echtem Multi-User-Bedarf — laut ROADMAP nicht vor 1.0).
