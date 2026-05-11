# Plan — Real Prod-Setup (Docker)

**Datum:** 2026-04-29 (Europe/Berlin)
**Branch-Konvention:** `ops/prod-image`
**Geltungsbereich:** Dockerfile, docker-compose.*.yml, Flask-Static-Serve, Gunicorn-Wiring, Smoke-Test

## Ziel

Echtes Prod-Image bauen: Vite-Build statt Devserver, Gunicorn statt Flask-Devserver, frontend statisch via Flask, ein einziger Container-Port (5001), HF-Cache-Mount aus aktuellem `docker-compose.yml`-Diff bleibt erhalten. Dev-Workflow (`docker compose up -d` mit Override) bleibt unangetastet.

## Architektur-Entscheidungen

- **Single-Container** (Flask serviert SPA + API). Kein separater Nginx — der Container sitzt bei dir bereits hinter Traefik/Nginx + Cloudflare.
- **Gunicorn mit `gevent`-Worker** wegen SSE (`/api/simulation/<id>/stream`); Sync-Worker würden Streams blockieren. `--timeout 0` für SSE-Verbindungen, gevent-Worker-Klasse hebt Limit faktisch auf.
- **Multi-Stage-Dockerfile**: Builder-Stage (Node → `npm run build:frontend`), Python-Stage (`uv sync` ohne dev-deps), Runtime-Stage (schlank, kein npm/node mehr drin).
- **Compose-Split**: `docker-compose.yml` (Basis, prod-tauglich) + `docker-compose.override.yml` (Dev, bleibt) + neu `docker-compose.prod.yml` (Prod-spezifische Overrides: keine Bind-Mounts, ggf. weniger Logging, gunicorn-CMD bleibt im Image).
- **SECRET_KEY / Auth**: keine Lockerungen — Prod erzwingt `AGORA_AUTH_TOKEN` (P0.1 ist scharf).

## Sub-Slices

### Slice 1 — Flask serviert das gebaute Frontend

- `backend/app/__init__.py`: `Flask(__name__, static_folder=<repo>/frontend/dist, static_url_path='/assets')` + Catch-all-Route `/` und `/<path:path>` → `index.html` (SPA-Fallback), API-Routes haben Vorrang (sie sind alle unter `/api/...`).
- Pfad-Resolver: `Config` bekommt `FRONTEND_DIST_DIR` (default `<repo>/frontend/dist`, env-overridable für Container).
- Tests: `tests/test_static_serve.py` — `GET /` liefert 200 mit `text/html`, `GET /api/status` weiterhin JSON, `GET /nonexistent` liefert SPA-Fallback (200, nicht 404).
- **Commit:** `feat(prod): serve built frontend from Flask with SPA fallback`
- **Arbeitsprotokoll:** `docs/2026-04-29-prod-slice1-static-serve.md`

### Slice 2 — Gunicorn + gevent dependency

- `backend/pyproject.toml`: `gunicorn>=23` und `gevent>=24` als runtime-deps.
- `backend/uv.lock` aktualisieren (`uv lock`).
- `backend/run_prod.py` **oder** Modul-Pfad `app:create_app` für Gunicorn-Factory-Mode (`gunicorn 'app:create_app()'`).
- Smoke lokal außerhalb Docker: `cd backend && uv run gunicorn -k gevent -w 2 -b 127.0.0.1:5001 --timeout 0 'app:create_app()'` → Health + Status grün.
- **Commit:** `feat(prod): add gunicorn+gevent runtime dependencies`
- **Arbeitsprotokoll:** `docs/2026-04-29-prod-slice2-gunicorn.md`

### Slice 3 — Multi-Stage Dockerfile

- Drei Stages:
  1. `frontend-build` (node:20-slim) — kopiert `frontend/`, `npm ci`, `npm run build` → `dist/`.
  2. `python-deps` (python:3.11-slim + uv) — kopiert `backend/pyproject.toml` + `uv.lock`, `uv sync --frozen --no-dev` → `.venv`.
  3. `runtime` (python:3.11-slim) — kopiert `.venv` aus Stage 2, `frontend/dist` aus Stage 1, `backend/` Sources, non-root-User, kein npm/node, CMD `gunicorn -k gevent -w 2 -b 0.0.0.0:5001 --timeout 0 'app:create_app()'`.
- Build-Args: `PYTHON_VERSION`, `NODE_VERSION` (default-pinned).
- `EXPOSE 5001` only (kein 5173 mehr im Prod-Image).
- HEALTHCHECK bleibt `curl -f http://localhost:5001/health`.
- Image-Größe-Ziel: < 800 MB (vs. aktuell ~2 GB Dev-Image).
- **Commit:** `feat(prod): multi-stage Dockerfile with vite build + gunicorn runtime`
- **Arbeitsprotokoll:** `docs/2026-04-29-prod-slice3-dockerfile.md`

### Slice 4 — Compose-Trennung Dev / Prod

- `docker-compose.yml` bleibt der **gemeinsame Basis-Stack** (neo4j, redis, agora-Service-Definition mit env, networks, security-opts, HF-Cache-Mount).
- `docker-compose.override.yml` bleibt **Dev**: Bind-Mounts + `command: npm run dev` (explizit setzen statt CMD-Default), Vite-Port-Mapping.
- Neu `docker-compose.prod.yml`: leeres Override oder enthält nur `restart: always` und Logging-Driver-Tweaks. Wichtig: Aktivierung via `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` — Override wird damit explizit übergangen.
- `docker-compose.yml` selbst: `command:` rausnehmen falls vorhanden, damit Image-CMD (gunicorn) greift; Vite-Port-Mapping nur in Override.
- README/CLAUDE.md/AGENTS.md: Prod-Befehl dokumentieren.
- **Commit:** `feat(prod): split compose into base/dev-override/prod-override`
- **Arbeitsprotokoll:** `docs/2026-04-29-prod-slice4-compose.md`

### Slice 5 — Smoke + Doku-Sync

- E2E-Smoke (manuell, dokumentiert):
  1. `docker compose -f docker-compose.yml -f docker-compose.prod.yml build agora`
  2. `... up -d`
  3. `curl /health`, `curl /api/status`, `GET /` (SPA), Upload-Roundtrip 1× Doku, Sim-Start, **SSE-Stream 60 s offen halten** (curl mit `-N`).
  4. Gunicorn-Worker-Reload (`docker compose kill -s HUP agora`) — SSE-Connections sollten neu aufgebaut werden, kein 5xx.
- `CLAUDE.md` + `AGENTS.md`: Prod-Setup-Sektion ergänzen, Dev-Sektion klarstellen.
- `CHANGELOG.md`: Entry für v0.6.x.
- **Commit:** `docs(prod): document prod compose workflow and smoke results`
- **Arbeitsprotokoll:** `docs/2026-04-29-prod-slice5-smoke.md`

## Risiken & offene Fragen

- **gevent + OASIS-Subprozess-IPC**: gevent monkey-patcht stdlib-sockets. `SimulationRunner` startet OASIS als getrenntes `subprocess.Popen` — sollte unkritisch sein, aber im Smoke explizit prüfen, dass Simulationen weiterhin sauber starten/beenden.
- **Embedding-Validierung beim Boot**: `create_app()` macht beim Start eine echte Embedding-Probe gegen Ollama. In Gunicorn-Multi-Worker-Mode passiert das pro Worker → 2× Probe beim Boot. Akzeptabel, aber im Smoke verifizieren dass kein Race entsteht.
- **`PYTHONDONTWRITEBYTECODE` + read-only rootfs** (aus aktueller `docker-compose.yml`): Gunicorn schreibt im Default keine pyc, also ok; aber `gevent` lädt cython-extensions, die sind im Wheel statisch.
- **HF-Cache-Mount**: aktueller Diff in `docker-compose.yml` zeigt auf `./backend/.cache/huggingface`. Im Prod-Compose unverändert lassen, aber Permission-Check (UID 1000 muss schreiben können — Hostpfad muss `chown 1000:1000` haben).
- **Frontend-API-Base-URL**: Vite-Build hardcoded keine API-Base, alles via relative `/api/...`. Wenn Flask die SPA serviert, klappt das automatisch — kein CORS-Issue. Verifizieren.

## Nicht-Ziele

- Kein separater Nginx-Container.
- Kein Pinning auf eine Cloud-Registry.
- Kein TLS im Container — bleibt Sache von Traefik/Cloudflare auf dem Host.
- Keine Änderungen an Auth/Token-Logik.

## Reihenfolge & Abhängigkeiten

```
Slice 1 (Static-Serve)  ──┐
                          ├──► Slice 3 (Dockerfile)  ──► Slice 4 (Compose)  ──► Slice 5 (Smoke + Docs)
Slice 2 (Gunicorn-Deps) ──┘
```

Slice 1 und 2 können parallel laufen (eigene Branches/Worktrees), müssen aber beide vor Slice 3 grün sein.
