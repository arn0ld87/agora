# Arbeitsprotokoll — Security-Followup S3

**Datum:** 2026-04-29 (Europe/Berlin)
**Slice:** S3 — Container Hardening (read-only rootfs, cap_drop, no-new-privileges)
**Plan:** [`docs/2026-04-29-security-followup-plan.md`](./2026-04-29-security-followup-plan.md)

## Was

Defense-in-Depth fürs Image-FS und Linux-Capabilities des `agora`-Service:

- `read_only: true` für die Container-Rootfs.
- `tmpfs` für die Schreibziele, die nicht im Bind-Mount liegen:
  - `/tmp` (`tempfile.NamedTemporaryFile` in `backend/app/api/report.py`).
  - `/app/backend/logs` (`backend/app/utils/logger.py:LOG_DIR`).
  - `/home/agora/.cache` (`uv` Tool-Cache; ohne den crashed `uv run python run.py` mit „Read-only file system" beim Boot).
  - `/home/agora/.npm` (npm-Cache).
- `security_opt: no-new-privileges:true`.
- `cap_drop: ALL` ohne `cap_add` — Live-Smoke hat gezeigt, dass kein einziger Cap nötig ist (dropdown vom konservativen Default `CHOWN/SETUID/SETGID/DAC_OVERRIDE` auf leer; Container bootet sauber, `/health` und `/api/status` antworten).
- `PYTHONDONTWRITEBYTECODE=1` damit Python nicht versucht, `__pycache__/*.pyc` neben den Sourcen ins Read-only-FS zu schreiben.

Alle Service-Schreibziele wurden vorher auditiert (`grep -rn "tempfile|os.makedirs|/tmp/" backend/app`):

| Pfad | Quelle | Lösung |
| --- | --- | --- |
| `Config.UPLOAD_FOLDER/projects` | `models/project.py` | bestehender Bind-Mount `./backend/uploads` |
| `Config.UPLOAD_FOLDER/run_registry` | `services/run_registry.py` | bestehender Bind-Mount |
| `Config.UPLOAD_FOLDER/reports` | `services/report_agent.py` | bestehender Bind-Mount |
| `Config.UPLOAD_FOLDER/simulations` | `services/simulation_manager.py` | bestehender Bind-Mount |
| `backend/logs` | `utils/logger.py:219` | neues tmpfs `/app/backend/logs` |
| `tempfile.NamedTemporaryFile` | `api/report.py:441` | neues tmpfs `/tmp` |
| `__pycache__/*.pyc` | Python-Default | `PYTHONDONTWRITEBYTECODE=1` |

## Geänderte Dateien

- [docker-compose.yml](../docker-compose.yml) — `read_only`, `tmpfs`, `security_opt`, `cap_drop`, `cap_add`, `PYTHONDONTWRITEBYTECODE`.

## Verifikation

- `docker compose config` clean — YAML merged korrekt mit Dev-Override.
- Live-Smoke 2026-04-29 08:25–08:26 Uhr durchgespielt:
  - Erster Recreate scheiterte mit `Failed to initialize cache at /home/agora/.cache/uv: Read-only file system` — `uv` braucht Schreibrechte im HOME-Cache. Behoben durch zusätzliche tmpfs für `/home/agora/.cache` und `/home/agora/.npm`.
  - Zweiter Recreate (mit konservativem `cap_add: [CHOWN, SETUID, SETGID, DAC_OVERRIDE]`): Backend startete sauber, Neo4j + Redis verbunden, Embedding validiert, `/health` 200, `/api/status` antwortet `backend.ok=True`, `neo4j.is_connected=True`.
  - Dritter Recreate (Cap-Trimming: `cap_add` komplett entfernt, nur `cap_drop: ALL`): Backend startet identisch sauber, `/health` 200, `/api/status` weiter grün. Damit ist der Cap-Set leer.

```bash
curl -fsS http://localhost:5001/health
# {"service":"Agora Backend","status":"ok"}
curl -fsS http://localhost:5001/api/status | jq '.backend.ok, .neo4j.is_connected'
# true / true
```

PDF-Upload + Graph-Build als End-to-End-Smoke werden vom User regulär getriggert; logs/-tmpfs und /tmp werden beim ersten ReportAgent-Lauf real geschrieben.

## Bekannte Caveats

- Dev-Override (`docker-compose.override.yml`) bind-mountet Repo-Root nach `/app`. Read-only wirkt damit primär auf Pfade außerhalb `/app` (System-Layer); `/app/backend/logs` und `/tmp` werden trotzdem als tmpfs angelegt. In Produktiv-Deployments ohne Override ist die Wirkung umfassender.
- `restart: unless-stopped` greift bei Permission-Fail-Restartloop. Nach Smoke beobachten, ob der Container ohne Restart-Loop bleibt.

## Status

**Done.** Patch + Live-Smoke + Cap-Minimierung in einem Slice durch.
