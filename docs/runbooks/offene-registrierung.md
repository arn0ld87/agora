# Offene Registrierung einrichten

Seit #1616 (ADR-0018, Plan §37) kann sich jeder mit bestätigter E-Mail-Adresse
registrieren. Er bekommt genau einen persönlichen Workspace. Zugang zu fremden
Workspaces vergeben nur deren Owner und Admins.

## 1) Ziel

Registrierung mit E-Mail-Bestätigung freischalten, ohne dass ein Konto ohne
bestätigte Adresse oder ein fremder Workspace erreichbar wird.

## 2) Voraussetzungen

- Der dedizierte Agora-Supabase-Stack aus `supabase/` läuft (`bootstrap.sh`).
  Den bestehenden Supabase-Stack anderer Anwendungen nicht für diese
  Registrierung umkonfigurieren.
- Die öffentliche Agora-Instanz hat eigene Artefakte, Neo4j und Redis. Alle
  fünf Metadaten-Backends zeigen auf **dieselbe dedizierte Supabase-Datenbank**,
  die auch GoTrue für `auth.users` nutzt. `DATABASE_URL` verwendet eine Rolle
  ohne RLS-Umgehung ([`rls-rollen.md`](rls-rollen.md)). Der bisherige
  persönliche Agora-Datenbestand bleibt in seiner internen Instanz.
- Host-Ports des dedizierten Supabase-Stacks (`POSTGRES_PORT`,
  `POOLER_PROXY_PORT_TRANSACTION`, `API_GW_HTTP_PORT`) sind gegenüber dem
  bestehenden Host-Stack eindeutig und nur an Loopback gebunden.
- Ein SMTP-Konto für Bestätigungs- und Reset-Mails.

## 3) Schritt-für-Schritt

1. SMTP und Registrierung in `supabase/.env` setzen:

   ```bash
   # Bestätigung ist Pflicht, sonst genügt eine fremde Adresse
   DISABLE_SIGNUP=false
   ENABLE_EMAIL_SIGNUP=true
   ENABLE_EMAIL_AUTOCONFIRM=false
   PASSWORD_MIN_LENGTH=12
   SMTP_HOST=<smtp-host>
   SMTP_PORT=587
   SMTP_USER=<smtp-user>
   SMTP_PASS=<smtp-passwort>
   SMTP_ADMIN_EMAIL=<absender@domain>
   # Ziel der Bestätigungslinks: die Agora-Oberfläche
   SITE_URL=https://<agora-host>
   ADDITIONAL_REDIRECT_URLS=https://<agora-host>/**
   # Die externe Auth-API enthält seit dem Self-Hosting-Update /auth/v1.
   API_EXTERNAL_URL=https://<agora-host>/auth/v1
   SUPABASE_PUBLIC_URL=https://<agora-host>
   ```

   Die Mail-Links setzt `supabase/docker-compose.yml` fest auf `/auth/v1/verify` (`GOTRUE_MAILER_URLPATHS_*`), weil GoTrue den Pfad absolut an `API_EXTERNAL_URL` anhängt. Kommt ausgehendes SMTP (Port 587) vom Host nicht durch, ist ein Relay nötig, sonst läuft `/signup` in einen 10-s-Timeout.

2. Das dedizierte Docker-Netz anlegen, den Supabase-Stack bootstrapen und mit
   dem öffentlichen Auth-Overlay starten. `AGORA_SUPABASE_BACKEND_NETWORK`
   muss in beiden Compose-Projekten denselben, nur für die Demo verwendeten
   Wert haben:

   ```bash
   docker network create agora-demo-backend
   cd supabase
   ./bootstrap.sh
   AGORA_SUPABASE_BACKEND_NETWORK=agora-demo-backend \
     docker compose -f docker-compose.yml -f docker-compose.public.yml up -d
   ```

3. JWT im Backend aktivieren (`.env` von Agora):

   ```bash
   AGORA_AUTH_BACKEND=hybrid
   AGORA_SUPABASE_JWT_ISSUER=https://<agora-host>/auth/v1
   AGORA_SUPABASE_JWT_SECRET=<JWT_SECRET aus supabase/.env>
   # Öffentlich, für den Browser-Client
   AGORA_SUPABASE_URL=https://<agora-host>
   AGORA_SUPABASE_ANON_KEY=<ANON_KEY aus supabase/.env>
   # Pflicht mit JWT
   AGORA_CORS_ALLOW_ALL=false
   ```

4. Backend neu starten und das Start-Log prüfen: Ein Konfigurationsfehler
   (fehlendes Backend auf `postgres`, `AGORA_ALLOW_ANONYMOUS`,
   `AGORA_CORS_ALLOW_ALL`) lässt JWT aus.

4. Erst nach erfolgreichen Backend- und Frontend-Gates die **getrennte**
   Agora-Instanz mit eigenem Compose-Projekt (`-p agora-demo`), Checkout,
   Artefaktverzeichnis, Neo4j, Redis und Netzwerk
   `AGORA_SUPABASE_BACKEND_NETWORK=agora-demo-backend` starten. Der Overlay
   [`deploy/compose/docker-compose.public.yml`](../../deploy/compose/docker-compose.public.yml)
   veröffentlicht nur diese Instanz auf `websecure`; der persönliche
   `agora`-Router bleibt auf `tswebsecure`.
   [`supabase/docker-compose.public.yml`](../../supabase/docker-compose.public.yml)
   veröffentlicht auf demselben Host **nur** `/auth/v1` über das Supabase-Gateway.
   PostgreSQL, Supavisor, Studio und alle übrigen Supabase-Pfade bleiben intern.
   Der öffentliche DNS-Eintrag von `<agora-host>` muss auf den öffentlichen
   Reverse-Proxy zeigen; eine Tailscale-Adresse ist von außen nicht erreichbar.
   Beide Overlays lesen den Host aus `AGORA_PUBLIC_HOST` in der `.env` des
   Demo-Checkouts und des Supabase-Stacks (Pflichtwert, z. B.
   `AGORA_PUBLIC_HOST=ag.agora.alexle135.de`). Liegt der Host zwei Ebenen unter
   der Zone (`ag.agora.…`), deckt das Cloudflare-Universal-Zertifikat
   (`*.alexle135.de`) ihn nicht ab: den Eintrag dann **DNS only** anlegen, das
   Zertifikat stellt Traefik (`letsencrypt`) aus.

   ```bash
   AGORA_SUPABASE_BACKEND_NETWORK=agora-demo-backend docker compose -p agora-demo \
     -f docker-compose.yml -f docker-compose.prod.yml \
     -f deploy/compose/docker-compose.prod-with-proxy.yml \
     -f deploy/compose/docker-compose.supabase.yml \
     -f deploy/compose/docker-compose.public.yml up -d --build
   ```

5. Im **Demo-Container** die kanonischen OpenAI-, Google- und MiniMax-
   Provider-Verbindungen ohne Betreiber-Key anlegen. Der idempotente Bootstrap
   verweigert vorhandene Betreiber-Secrets und fremde Base-URLs. Danach kann
   jeder bestätigte Nutzer Modelle nur mit seinem eigenen Key abrufen:

   ```bash
   docker compose -p agora-demo -f docker-compose.yml -f docker-compose.prod.yml \
     -f deploy/compose/docker-compose.prod-with-proxy.yml \
     -f deploy/compose/docker-compose.supabase.yml \
     -f deploy/compose/docker-compose.public.yml \
     exec agora uv run python scripts/bootstrap_public_demo_providers.py
   ```

   Embeddings laufen für alle Besucher über den Betreiber-Endpoint auf gns3
   (llama.cpp, `qwen3-embedding:4b`, 2560 Dimensionen). Die Demo-`.env` setzt
   dafür `EMBEDDING_BASE_URL` (Tailnet-URL des gns3-Endpoints),
   `EMBEDDING_MODEL=qwen3-embedding:4b`, `VECTOR_DIM=2560` und
   `EMBEDDING_API_KEY` (Vaultwarden `GNS3_EMBEDDING_API_KEY`); das Overlay
   bricht ohne diese Werte ab und gibt genau diese URL per
   `AGORA_SHARED_EMBEDDING_BASE_URL` frei. Das Overlay erzwingt leere globale
   Cloud-Provider-Variablen. Es begrenzt CPU, RAM und Prozesse der Demo-Container,
   drosselt kostspielige Starts und aktiviert JWT-Demo-Limits für Runden und
   Laufbudgets. Die Betreiber-Instanz bleibt in ihrem eigenen Compose-Projekt.

   Die `.env` des Demo-Checkouts darf keine der folgenden Variablen enthalten:
   `LLM_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`,
   `MINIMAX_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`,
   `OLLAMA_API_KEY`, `LLM_BOOST_API_KEY`, `LLM_BASE_URL`,
   `LLM_BOOST_BASE_URL`, `TAVILY_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`,
   `OLLAMA_BASE_URL`, `OPENAI_BASE_URL`, `OPENAI_API_BASE_URL`. Dasselbe gilt
   für `backend/instance/settings.json` des Demo-Checkouts: dort persistierte
   Keys zählen wie Env-Vars. Im Demo-Modus (`AGORA_DEMO_MODE=true`) verweigert das
   Backend sonst den Start (#1688) — Besucher-Keys leben ausschließlich im
   verschlüsselten Workspace-Credential-Store, nie in der Prozessumgebung des
   Betreibers. `enable_graph_memory_update` steht Besuchern nicht zur
   Verfügung.

## 4) Überprüfung

```bash
# Erwartet: "jwt_enabled": true und die beiden öffentlichen Angaben
curl -s https://<agora-host>/api/auth/config

# Registrierung ohne Bestätigung liefert kein access_token
curl -s -X POST https://<agora-host>/auth/v1/signup \
  -H "apikey: <ANON_KEY>" -H 'Content-Type: application/json' \
  -d '{"email":"test@example.org","password":"mindestens-12-zeichen"}'

# Nach Bestätigung und Login: persönlicher Workspace, beim zweiten Aufruf created=false
curl -s -X POST https://<agora-host>/api/workspaces/bootstrap \
  -H "Authorization: Bearer <access_token>" -H 'Content-Type: application/json' -d '{}'
```

Danach im Browser mit einem bestätigten Testkonto anmelden, unter
`/workspace/provider-keys` einen **eigenen** Provider-Key speichern und einen
Provider und ein Modell auswählen und einen Graph-/Berichtslauf starten. Der Lauf muss ohne Browser-Konsole und ohne
`AGORA_AUTH_TOKEN` funktionieren. Mit einem zweiten Konto kontrollieren, dass
der erste Workspace, seine Artefakte und sein Key weder sichtbar noch nutzbar
sind. Den Test-Key danach löschen. Eine ungeprüfte Veröffentlichung der
Bestandsdaten ist kein Abnahmekriterium.

## 5) Warum?

Ohne Bestätigung könnte jeder mit einer fremden Adresse ein Konto anlegen. Der
persönliche Workspace hängt an der Nutzer-ID; deshalb ist der Bootstrap
idempotent und öffnet keinen fremden Workspace. Registrierung schließen:
`DISABLE_SIGNUP=true`, bestehende Konten bleiben gültig.

## 6) Nächste Schritte

- Mitglieder einladen: `PUT /api/workspaces/current/members/<user_id>` als Owner oder Admin.
- Frontend-Login über den Supabase-Client (#1617).
- Realtime für Listen-Projektionen: [`supabase/README.md`](../../supabase/README.md#realtime-1618), Schalter `AGORA_SUPABASE_REALTIME`.
