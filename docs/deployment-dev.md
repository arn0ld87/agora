# Deployment — Dev

**Stand:** 2026-08-11, Europe/Berlin
**Scope:** Lokaler Entwicklungsbetrieb auf einer Single-User-Maschine. Zwei
Pfade: bare-metal mit `bun run dev` und Docker-Compose-Dev-Stage. Beide laufen
gegen `127.0.0.1`, beide nutzen Hot-Reload.

> **Paketmanager ist `bun`, nicht `npm`.** Root und Frontend halten je eine
> `bun.lock`; eine `package-lock.json` gibt es nicht. Wer `npm install` fährt,
> erzeugt einen zweiten, nicht committeten Lockfile-Pfad. Der bequemste
> Einstieg ist `./install.sh` (Host-Modus) bzw. `./install.sh --docker`.

Für Prod-Härtung (Gunicorn, Reverse-Proxy, restriktive CORS) siehe
[`deployment-prod-like.md`](deployment-prod-like.md).

---

## Voraussetzungen

| Komponente | Mindestversion | Zweck |
|---|---|---|
| `bun` | 1.3.0+ | Paketmanager und Task-Runner (`engines.bun` in beiden `package.json`) |
| Node.js | 20.x+ | Laufzeit für Vite und die Test-Runner (`engines.node`) |
| Python | 3.14 (`>=3.14,<3.15`) | Backend-Runtime, gepinnt in `backend/pyproject.toml` |
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

## Pfad A — Bare-Metal (`bun run dev`)

Schnellster Pfad für aktive Entwicklung. Kein Container, kein Build-Layer.

### Setup

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
cp .env.example .env

# Dependencies (root + frontend + backend)
bun run setup:all
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
bun run dev
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
bun run check
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
| `agora` (Vite) | `AGORA_FRONTEND_PORT`, Default 5173 | `AGORA_BIND_HOST`, Default 127.0.0.1 | Frontend Hot-Reload |
| `agora` (Flask) | `AGORA_BACKEND_PORT`, Default 5001 | `AGORA_BIND_HOST`, Default 127.0.0.1 | API + `/health` |
| `neo4j` (Browser) | 7474 (fest) | 127.0.0.1 (fest) | Neo4j-Web-UI |
| `neo4j` (Bolt) | 7687 (fest) | 127.0.0.1 (fest) | Bolt-Treiber |
| `redis` | — | nur Compose-intern | Event-Bus + Tickets |

Die drei `AGORA_*`-Variablen stehen auskommentiert in `.env.example`. Der
Default `127.0.0.1` ist die sichere Wahl; ihn zu ändern öffnet den Stack auf
LAN- oder Tailscale-Interfaces.

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

### Read-Only-Rootfs — nur im Prod-Compose

Der Dev-Stack setzt bewusst `read_only: false` (`docker-compose.yml`), damit
Hot-Reload und Zwischenartefakte nicht an Mount-Grenzen scheitern. Erst
`docker-compose.prod.yml` schaltet `read_only: true`; dort sind nur explizite
`tmpfs`-Mounts (`/tmp`, `/app/backend/logs`, Caches) und die oben gelisteten
Volumes schreibbar.

Wer eine Änderung gegen den Prod-Pfad absichern will, testet sie deshalb mit
`docker-compose.prod.yml` — im Dev-Stack fällt ein neues Schreibziel nicht auf.
Kommt eines dazu, gehört der Mount ins Compose oder der Pfad geändert — nicht
das Read-Only-Flag.

### Der `backend/.cache`-Bind gehört danach root

`./backend/.cache/huggingface` ist ein Bind-Mount. Legt der Container das
Verzeichnis an, gehört `backend/.cache` auf dem Host anschließend `root` — und
Host-Werkzeuge, die darunter schreiben wollen, brechen ab. Betroffen ist unter
anderem `scripts/sync-status.sh`, das seinen Zähler-Cache in
`backend/.cache/sync-status/` ablegt und dann mit „Keine Berechtigung"
aussteigt.

```bash
sudo chown -R "$USER" backend/.cache    # oder: sudo rm -rf backend/.cache
```

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
