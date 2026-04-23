# Changelog

Alle nennenswerten Änderungen an Agora werden hier dokumentiert.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach [SemVer](https://semver.org/lang/de/).

## [0.4.1] — 2026-04-23

### Hinzugefügt
- fail-fast Validierung für `EMBEDDING_MODEL` / `VECTOR_DIM` inklusive echter Embedding-Probe beim Backend-Start
- `frontend/src/composables/usePolling.js` als gemeinsamer Polling-Baustein für Langläufer
- `backend/app/utils/json_io.py` für atomische JSON-Schreibvorgänge und defensive Reads
- `docu/README.md` sowie `docs/README.md` als klarerer Einstieg in die neue Dokumentationsstruktur

### Geändert
- Report-Status-Polling ist robuster gegen leere/trunkierte `progress.json` / `meta.json`
- Simulation-nahe JSON-Artefakte (`state.json`, `run_state.json`, `simulation_config.json`, `reddit_profiles.json`) werden defensiver gelesen und teils atomisch geschrieben
- Root von temporären Hilfsdateien entlastet; historische Notizen liegen jetzt unter `docu/history/`, Log-Helfer unter `scripts/logs/`
- Dokumentationsbestand weiter nach `docu/` konsolidiert

### Test-Status
- 70/70 Backend-Tests grün
- Frontend-Lint: 0 Fehler (21 Warnungen)
- Frontend-Build: erfolgreich

## [0.4.0] — 2026-04-22

Scope-Fokus: **Operability, Refactoring-Basis & Resilienz**. Details siehe `docu/plan_0.4.md` sowie die P0-Protokolle unter `docu/`.

### Hinzugefügt
- `GET /api/status` — konsolidierter Ops-Endpoint mit `backend`, `neo4j`, `ollama`, `disk`, `gpu`, `timestamp` (`backend/app/api/status.py`, 7 Tests)
- `backend/app/utils/gpu_probe.py` — `detect_gpu()` erkennt `nvidia-smi` und parst `ollama ps` (wirft nie, 8 Tests)
- `AGORA_LOG_FORMAT=text|json` Env-Toggle — Opt-in JSON-Logging via neuem `JSONFormatter` in `backend/app/utils/logger.py` (stdlib-only, 10 Tests)
- Request-ID-Middleware in `backend/app/__init__.py` (8-Zeichen-UUID, loggt bei `after_request`)
- `simulation_id`-Context in Simulation-Logs (`simulation_runner.py`, `api/simulation.py`)
- Kommentierte GPU-Reservation-Sektion in `docker-compose.yml` + README-Abschnitt „GPU/CPU Fallback"

### Geändert
- `Neo4jStorage` mit transientem Retry (`ServiceUnavailable`, `SessionExpired`, `TransientError`, exp. Backoff + Jitter, max 3 Retries) — via neuem `neo4j_call_with_retry` in `backend/app/utils/retry.py`
- Neue Read-only-Properties auf `Neo4jStorage`: `is_connected`, `last_error`, `last_success_ts` — vom `/api/status`-Endpoint konsumiert
- `get_ontology()` und `search()` durchlaufen jetzt das Retry-Wrapper
- Root-Quality-Gates vereinheitlicht (`npm run check`, Backend-Ruff scoped rollout, Frontend-ESLint, CI-Workflow)
- `backend/app/api/simulation.py` in fokussierte Module zerlegt (`simulation_lifecycle`, `simulation_prepare`, `simulation_profiles`, `simulation_run`, `simulation_interviews`, `simulation_history`)
- `frontend/src/components/GraphPanel.vue` in erste Teilmodule zerlegt (Detailpanel, Legende, Datenaufbereitung)

### Verschoben
- Python-3.12/CAMEL/OASIS-Kompatibilität → v0.4.1/v0.5 (Upstream-blockiert, Host-Python im Container irrelevant)

### Test-Status
- 63/63 Backend-Tests grün
- Frontend-Lint: 0 Fehler (verbleibende Warnungen dokumentiert und schrittweise abzubauen)
- Frontend-Build: erfolgreich

### Entwicklungs-Vorgehen
- Feature-Arbeit parallel über isolierte Git-Worktrees: Haiku 4.5 für GPU-Probe + `/api/status`, Sonnet 4.6 für Neo4j-Reconnect + JSON-Logging
- Merges als `--no-ff` in main, GPU-Detect in `/api/status` nachverdrahtet

## [0.3.1] — 2026-04-22

### Geändert
- **Logo & Favicon**: Agora-Branding auf neues Logo (`media/logo.png`, 1254×1254) umgestellt
  - `frontend/public/icon.png` (Favicon, 256×256)
  - `frontend/src/assets/logo/agora-logo.jpg` (Home-View, 1024×1024)
  - `static/image/agora-logo.jpg` + `agora-logo-source.jpg` (README/Banner-Assets)
  - Commits: `97aca71` → Rebase auf `2dd1e58`

## [0.3.0] — vorher

Siehe Git-Historie vor Einführung dieses Changelogs.
