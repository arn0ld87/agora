# Deployment — Prod-Like

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Scope:** gehärteter Single-User-/Single-Tenant-Betrieb hinter Tailnet oder Reverse Proxy. Kein Multi-User-AuthN-System.

Für Entwicklung: [`deployment-dev.md`](deployment-dev.md). Für Betrieb/Recovery: [`operations.md`](operations.md), [`backup-restore.md`](backup-restore.md).

> [!IMPORTANT]
> „Prod-like“ bedeutet: bekannte Hardening-Maßnahmen aktiv, aber weiterhin Single-User-Vertrauensmodell. Eine Instanz ohne geeignete Netzwerk-/TLS-/Auth-Grenze direkt ins Internet zu hängen ist nicht der unterstützte Zielbetrieb.

---

## Voraussetzungen

- Docker + Compose v2
- Git
- Reverse Proxy/Tailnet für Remote-Zugriff
- Neo4j gemäß Compose-Pin
- Redis gemäß Compose
- mindestens ein funktionsfähiger LLM-/Embedding-Pfad (HTTP/local/CLI je nach Setup)

Ollama ist **eine** Provideroption, keine zwingende globale Voraussetzung. Ein Run kann z. B. über eine Cloud- oder CLI-Route laufen.

---

## Installation

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
./install.sh
```

`install.sh` erzeugt `.env` und sichere Werte für `SECRET_KEY`, `AGORA_AUTH_TOKEN`, `AGORA_SECRET_KEY` und `AGORA_FERNET_KEY` (#1483). Anschließend `NEO4J_PASSWORD` und die tatsächlich benötigte Provider-/Embedding-Konfiguration setzen.

---

## Compose-Prod-Pfad

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  up -d --build
```

Der Prod-Override zielt auf:

- `build.target: prod`
- gebautes Frontend statt Vite-Devserver
- Backend-Hostport auf Loopback
- Neo4j ohne unnötige Hostports
- read-only Root-Filesystem mit expliziten Write-Pfaden/tmpfs
- `init: true`
- `stop_grace_period: 45s`

Die **tatsächliche** wirksame Konfiguration vor jedem Deployment prüfen:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  config
```

Nicht davon ausgehen, dass ein altes Doku-Snippet Vorrang vor dem gerenderten Compose hat.

---

## Gunicorn: ein Worker ist Absicht

Die produktive Gunicorn-Konfiguration verwendet aktuell:

```text
worker_class = gevent
workers = 1
preload_app = True
```

`workers=1` ist ein **HARDSTOP**. Prozesslokale RunRegistry-/Monitor-/Cancel-/Jobanteile machen mehrere Webworker derzeit semantisch unsicher.

### Nicht tun

```text
„Report langsam → workers=4“
```

Das kann nicht nur nichts lösen, sondern Zustandswahrheiten vervielfachen.

### Performance-Folge

CPU-schwere parallele Reports konkurrieren im einzelnen gevent-Worker. [#1265](https://github.com/arn0ld87/agora/issues/1265) dokumentiert deutlich erhöhte Laufzeiten. Bis zur Prozess-/Queue-Entkopplung schwere Reports möglichst serialisieren.

---

## Restart-/Shutdown-Verhalten

### Simulation

Seit #1474/#1476:

- expliziter Nutzer-Stop → `stopped/user_stop`
- Force-Restart nutzt Generation-Tokens gegen stale Monitore
- Startup-Reconciliation läuft unter Gunicorn in `post_fork`
- tote persistierte Simulations-PIDs können `failed/process_restart` werden
- frisches PID-loses `STARTING` erhält eine 30-s-Grace-Period

### Prepare / Report / Graph

Weiter offen: [#1472](https://github.com/arn0ld87/agora/issues/1472). Diese Jobs laufen als daemonisierte Threads im Webprozess und besitzen noch keinen vollständig persistenten Interrupted-/Resume-Lifecycle.

Deshalb Deploy/Recreate möglichst **nicht mitten in diesen Jobs** auslösen.

---

## Ports und Netzwerk

Im unterstützten Prod-like-Muster:

| Service | Host-Exposure |
|---|---|
| Agora | Loopback-Port, typischerweise `127.0.0.1:5001` |
| Neo4j | Compose-intern bzw. bewusst getunnelt |
| Redis | Compose-intern |

Remote-Zugriff erfolgt über Tailnet/Reverse Proxy.

`AGORA_BIND_HOST=0.0.0.0` ist ein bewusster Exposure-Entscheid und soll nicht versehentlich gesetzt werden.

---

## Sidecar-Nginx

Der Repo-Pfad mit Proxy-Override:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f deploy/compose/docker-compose.prod-with-proxy.yml \
  up -d --build
```

Typische Checks:

```bash
curl -fsS http://127.0.0.1:${AGORA_PROXY_PORT:-8080}/healthz
curl -fsS http://127.0.0.1:${AGORA_PROXY_PORT:-8080}/health
curl -fsS http://127.0.0.1:${AGORA_PROXY_PORT:-8080}/
```

HTTPS-Termination bleibt Aufgabe der äußeren Grenze (z. B. Tailscale, Cloudflare Tunnel, separater TLS-Reverse-Proxy).

---

## SSE / Reverse Proxy

Live-Streams benötigen:

- lange Read-Timeouts
- deaktiviertes Response-Buffering
- Weitergabe der relevanten Forwarded-Header

Für Nginx typischerweise:

```nginx
proxy_http_version 1.1;
proxy_read_timeout 1h;
proxy_buffering off;
proxy_set_header X-Forwarded-Proto https;
```

Die konkrete Proxy-Konfiguration muss zum tatsächlichen TLS-/Host-Setup passen.

---

## Auth

Prod-like benötigt ein gültiges `AGORA_AUTH_TOKEN`. Unterstützte Header stehen in [`auth.md`](auth.md); bevorzugt:

```http
Authorization: Bearer <token>
```

`X-Agora-Token` bleibt Backward-Compat.

Zusätzliche Workspace/API-Keys besitzen eigene Scope-Semantik.

### Nicht in Prod

- `FLASK_DEBUG=true`
- `AGORA_ALLOW_ANONYMOUS=true`
- `AGORA_CORS_ALLOW_ALL=true`, sofern nicht für einen bewusst isolierten Sonderfall

---

## Provider-Runtime

Prod-like zwingt nicht alle Stages auf `LLM_BASE_URL`.

Runtime-Auflösung:

```text
AiRoute/LlmRoute
  → ProviderConnection
  → SecretResolver
  → transport (http | local | cli)
```

`codex_cli` besitzt `transport=cli`, `auth_mode=session`, keine Base-URL. Details: [`provider-runtime-settings.md`](provider-runtime-settings.md).

---

## Embeddings

Bekannte Grenze [#1417](https://github.com/arn0ld87/agora/issues/1417): Die UI-Aktivierung einer Embedding-Konfiguration steuert noch nicht garantiert jeden produktiven Runtime-Consumer.

Vor Prod-Deploy nach Embedding-Wechsel:

- Store und `.env` vergleichen
- Modell/Endpoint/Dimension verifizieren
- Migration-Lifecycle abschließen
- Retrieval-Smoke durchführen

---

## Daten und Write-Pfade

Persistente Bereiche umfassen mindestens:

- `backend/uploads/`
- `backend/uploads/reports/`
- `backend/data/`
- `backend/instance/`
- Neo4j-Volume

Reports liegen **nicht** unter `backend/reports/` (#1483).

Read-only Root-FS bedeutet: Neue Codepfade dürfen nicht still irgendeinen zusätzlichen Schreibpfad unter `/app` erfinden. Write-Roots müssen im Compose/ArtifactStore vorgesehen sein.

---

## Backup vor Update

Vor jedem Prod-like-Update:

- Neo4j konsistent sichern
- `backend/uploads/`, `backend/data/`, `backend/instance/` sichern
- `.env`/Master-Keys recoverbar halten
- aktuellen Git-/Versionsstand notieren

Siehe [`backup-restore.md`](backup-restore.md).

---

## Update

```bash
git fetch origin
git log --oneline HEAD..origin/main
git pull --ff-only origin main

docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  up -d --build
```

Danach:

```bash
curl -fsS http://localhost:5001/health
curl -fsS \
  -H "Authorization: Bearer $AGORA_AUTH_TOKEN" \
  http://localhost:5001/api/status
```

Migrationsschritte nur ausführen, wenn die konkrete Release-Doku sie verlangt. Kein generisches Fantasie-`migrate` als religiöses Ritual.

---

## Release-/CI-Hinweis

Workflows und Required Checks können sich ändern; `.github/workflows/` und Branch-Regeln sind die operative Wahrheit. September-PRs dokumentierten zeitweise eingeschränkte PR-Actions wegen Billing, während scheduled E2E weiterhin liefen. Deshalb Releaseaussagen immer auf den **konkreten Head und konkreten Check-Run** beziehen.

Für `1.0.0` verlangt #767 vollständig grüne erforderliche Gates sowie Fresh-Install-/Restore-/Upgrade-/Rollback-Nachweise.

---

## Prod-like DoD

- [ ] `.env` ohne Placeholder-Secrets
- [ ] `NEO4J_PASSWORD` gesetzt
- [ ] `/health` grün
- [ ] `/api/status` mit Auth plausibel
- [ ] wirksames `docker compose config` geprüft
- [ ] Backend nur bewusst exponiert
- [ ] Neo4j/Redis nicht unnötig öffentlich
- [ ] ProviderRoute/Connection getestet
- [ ] Embedding-Runtime nach Modellwechsel verifiziert
- [ ] Backup-Punkt vorhanden
- [ ] keine laufenden daemonisierten Jobs beim Recreate

Für 0.10/1.0 kommen die zusätzlichen Release-Gates aus [`ROADMAP.md`](../ROADMAP.md) dazu.
