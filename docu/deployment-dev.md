# Deployment — Dev

**Stand:** 2026-05-01, Europe/Berlin
**Scope:** Lokaler Entwicklungsbetrieb auf einer Single-User-Maschine. Zwei
Pfade: bare-metal mit `npm run dev` und Docker-Compose-Dev-Stage. Beide laufen
gegen `127.0.0.1`, beide nutzen Hot-Reload.

Für Prod-Härtung (Gunicorn, Reverse-Proxy, restriktive CORS) siehe
[`deployment-prod-like.md`](deployment-prod-like.md).

---

## Voraussetzungen

| Komponente | Mindestversion | Zweck |
|---|---|---|
| Node.js | 18.x | Vite, Frontend-Build, Test-Runner |
| `npm` | mit Node geliefert | `package-lock.json`-Pfad |
| Python | 3.11 | Backend-Runtime |
| `uv` | 0.4+ | Python-Dependency-Manager (statt `pip`/`venv`) |
| Neo4j | 5.18+ | Graph-Storage. Lokal oder via Compose. |
| Ollama | aktuell | LLM + Embedding. Auf dem Host, nicht im Container. |
| Docker / Compose | optional | Compose-Dev-Pfad braucht v2.24+ wegen `!override`/`!reset`. |
| Redis | optional | Single-Use-Tickets + Event-Bus. Compose startet Redis automatisch. |

`uv` installieren (einmalig):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Ollama-Modelle ziehen (einmalig):

```bash
ollama pull qwen2.5:32b              # oder ein leichteres Modell
ollama pull qwen3-embedding:4b       # 2560-dim, erfordert VECTOR_DIM=2560
# Fallback: ollama pull nomic-embed-text  # 768-dim, VECTOR_DIM=768
```

---

## Pfad A — Bare-Metal (`npm run dev`)

Schnellster Pfad für aktive Entwicklung. Kein Container, kein Build-Layer.

### Setup

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
cp .env.example .env

# Dependencies (root + frontend + backend)
npm run setup:all
```

`.env` minimal anpassen:

```env
FLASK_DEBUG=true                     # Dev: Tracebacks + Reloader, blockt Placeholder-Reject nicht
SECRET_KEY=change-me-use-token_urlsafe-32   # Dev darf Placeholder bleiben, Config.validate() warnt
NEO4J_PASSWORD=<dein_lokales_neo4j_pw>
LLM_BASE_URL=http://localhost:11434/v1
NEO4J_URI=bolt://localhost:7687
EMBEDDING_BASE_URL=http://localhost:11434
```

Token-Auth optional, siehe Abschnitt
[Auth-Token im Dev-Modus](#auth-token-im-dev-modus).

### Start

```bash
npm run dev
```

Startet Backend und Frontend parallel über `concurrently`:

| Endpoint | URL | Bind |
|---|---|---|
| Frontend (Vite) | <http://localhost:5173> | 127.0.0.1 |
| Backend (Flask) | <http://localhost:5001/health> | 127.0.0.1 |

Hot-Reload greift in beide Richtungen. Backend-Reload via `werkzeug` ist nur
mit `FLASK_DEBUG=true` aktiv.

### Lokales Neo4j

Variante 1 — Neo4j-Desktop oder System-Service:

```bash
# Beispiel Arch / Cachy
sudo systemctl start neo4j
# Browser: http://localhost:7474, Credentials wie in .env
```

Variante 2 — nur Neo4j aus Compose ziehen (Backend bleibt bare-metal):

```bash
docker compose up -d neo4j redis
# Beide binden auf 127.0.0.1 (siehe docker-compose.yml).
# Backend-`NEO4J_URI` bleibt `bolt://localhost:7687`.
```

### Tests + Lint

```bash
npm run check
```

Stufen: Backend-Lint (`ruff check app/ tests/`), Backend-Tests (`pytest`),
Frontend-Lint (ESLint), Frontend-Tests (Vitest auf `jsdom`),
Frontend-Build. Pre-Commit-Gate für jeden Slice. Zwei Redis-Integrationstests
skippen sauber, wenn `TEST_REDIS_URL` nicht gesetzt ist.

---

## Pfad B — Docker Compose (`target: dev`)

Compose-Stack mit Backend, Frontend, Neo4j und Redis. Default-Compose nutzt
seit v0.9.0 explizit den `dev`-Stage aus dem Multi-Stage-Dockerfile (Vite +
Flask, Hot-Reload, kein Gunicorn).

### Setup

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
cp .env.example .env
# Pflichtwert: NEO4J_PASSWORD. Compose bricht sonst ab (`:?`-Syntax).
```

### Start

```bash
docker compose up -d --build
docker compose logs -f agora        # Live-Log
```

Was läuft:

| Service | Port (Host) | Bind | Zweck |
|---|---|---|---|
| `agora` (Vite) | 5173 | 127.0.0.1 | Frontend Hot-Reload |
| `agora` (Flask) | 5001 | 127.0.0.1 | API + `/health` |
| `neo4j` (Browser) | 7474 | 127.0.0.1 | Neo4j-Web-UI |
| `neo4j` (Bolt) | 7687 | 127.0.0.1 | Bolt-Treiber |
| `redis` | — | nur Compose-intern | Event-Bus + Tickets |

Container-zu-Container-Verbindungen laufen über das Compose-Netzwerk und
brauchen die Host-Ports nicht. Die Loopback-Bindings sind explizit gewählt,
damit der Stack nicht versehentlich auf Tailscale/LAN-Interfaces hört. Wer
LAN-Zugriff will, setzt einen Reverse-Proxy davor — siehe
[`deployment-prod-like.md`](deployment-prod-like.md).

Ollama läuft auf dem Host und wird über `host.docker.internal` (im Compose
als `extra_hosts: host-gateway` aufgelöst) erreicht. Im Container überschreibt
Compose `LLM_BASE_URL`, `NEO4J_URI` und `EMBEDDING_BASE_URL`, sodass die
`localhost`-Defaults in `.env` für den Bare-Metal-Pfad nutzbar bleiben.

### Häufige Dev-Kommandos

```bash
# Container neu starten ohne Image-Rebuild
docker compose up -d --force-recreate agora

# Image rebuilden (z. B. nach Dependency-Bump)
docker compose build agora && docker compose up -d --force-recreate --no-deps agora

# Volumes resetten (Achtung: löscht Neo4j-Daten und Cache)
docker compose down -v && docker compose up -d
```

### Volumes

| Volume | Zweck |
|---|---|
| `./backend/uploads` (Bind) | Hochgeladene Dokumente. Nicht versioniert. |
| `./backend/.cache/huggingface` (Bind) | OASIS-Modelle (~1 GB). Persistiert über Restarts. |
| `neo4j_data` (Named) | Neo4j-Datenbank. |
| `neo4j_logs` (Named) | Neo4j-Logs. |
| `redis_data` (Named) | Redis-Persistenz (RDB-Snapshots). |

### Read-Only-Rootfs

Der `agora`-Container läuft mit `read_only: true`. Schreibbar sind nur
explizite `tmpfs`-Mounts (`/tmp`, `/app/backend/logs`, Caches) und die oben
gelisteten Volumes. Wenn beim Dev-Pfad neue Schreibziele dazukommen, muss der
Mount im Compose oder im Code geändert werden — nicht das Read-Only-Flag.

---

## Auth-Token im Dev-Modus

Im Dev-Default ist `AGORA_AUTH_TOKEN` leer und das Backend läuft im Open-Mode
mit Log-Warning. Für eine echte Token-Schleife siehe
[`auth.md`](auth.md). Kurzfassung:

```bash
# Token erzeugen
AGORA_AUTH_TOKEN=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
echo "AGORA_AUTH_TOKEN=$AGORA_AUTH_TOKEN" >> .env

# Frontend-Storage (Browser-Devtools auf http://localhost:5173):
localStorage.setItem('agora_token', '<derselbe_wert>')
```

Prod-Empfehlung ist Memory-Mode (`VITE_AGORA_TOKEN_STORAGE=memory`) statt
`localStorage` — siehe [`auth.md`](auth.md), Abschnitt „Frontend-Token-Storage".

---

## Bekannte Dev-Stolperfallen

- **`NEO4J_PASSWORD` fehlt:** Compose bricht beim `up` mit Fehlermeldung ab.
  Nicht-Debug-Backend rejected zusätzlich Placeholder (`agora`, `neo4j`,
  `password`). Im Dev-Modus (`FLASK_DEBUG=true`) läuft es mit Warning
  durch. Siehe [`security-hardening.md`](security-hardening.md), Phase 1.
- **Embedding-Mismatch:** `EMBEDDING_MODEL` und `VECTOR_DIM` müssen
  zusammenpassen (`qwen3-embedding:4b` ↔ `2560`, `nomic-embed-text` ↔ `768`).
  Backend probet beim Start; Mismatch blockiert den Start.
- **Ollama nicht erreichbar:** `/api/status` zeigt `ollama_uses_gpu: null`.
  Im Compose-Pfad: `host.docker.internal` muss vom Container zum Host
  auflösen — Linux braucht `extra_hosts: host-gateway` (ist im Compose
  gesetzt).
- **Vite-Port belegt:** Vite zieht selbst auf den nächsten freien Port hoch,
  Backend kennt aber nur `5173` für CORS. Belegten Port abräumen statt Vite
  ausweichen lassen, oder `AGORA_EXTRA_ORIGINS` setzen.
- **Read-Only-Rootfs + neuer Schreibpfad:** Dev-Setups, die plötzlich `EROFS`
  liefern, brauchen einen tmpfs- oder Volume-Mount im Compose. Siehe
  Abschnitt „Volumes".

---

## Verweise

- [`auth.md`](auth.md) — Token-Header, Ticket-Flow, Storage-Optionen.
- [`security-hardening.md`](security-hardening.md) — Secure-Defaults,
  Placeholder-Reject, CORS-Whitelist, SSRF-Blocker.
- [`deployment-prod-like.md`](deployment-prod-like.md) — Gunicorn,
  Reverse-Proxy, Compose-Prod-Override.
- [`dependency-risk-register.md`](dependency-risk-register.md) — aktiv
  gepinnte CVEs.
