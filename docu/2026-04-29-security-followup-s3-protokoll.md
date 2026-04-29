# Arbeitsprotokoll — Security-Followup S3

**Datum:** 2026-04-29 (Europe/Berlin)
**Slice:** S3 — Container Hardening (read-only rootfs, cap_drop, no-new-privileges)
**Plan:** [`docu/2026-04-29-security-followup-plan.md`](./2026-04-29-security-followup-plan.md)

## Was

Defense-in-Depth fürs Image-FS und Linux-Capabilities des `agora`-Service:

- `read_only: true` für die Container-Rootfs.
- `tmpfs` für die drei Schreibziele, die nicht im Bind-Mount liegen:
  - `/tmp` (`tempfile.NamedTemporaryFile` in `backend/app/api/report.py`).
  - `/app/backend/logs` (`backend/app/utils/logger.py:LOG_DIR`).
  - `/app/.npm` (npm cache; npm legt Cache standardmäßig in `$HOME/.npm`).
- `security_opt: no-new-privileges:true`.
- `cap_drop: ALL` plus konservatives `cap_add`-Set (`CHOWN`, `SETUID`, `SETGID`, `DAC_OVERRIDE`) — passend zu User-Switch (`useradd`+`USER agora`) und npm-Install-Spuren.
- `PYTHONDONTWRITEBYTECODE=1` damit Python nicht versucht, `__pycache__/*.pyc` neben den Sourcen ins Read-only-FS zu schreiben.

Alle Service-Schreibziele wurden vorher auditiert (`grep -rn "tempfile|os.makedirs|/tmp/" backend/app`):

| Pfad | Quelle | Lösung |
|---|---|---|
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
- **Live-Smoke ausstehend.** Aktueller `agora`-Container läuft seit 4h healthy mit aktiven Sessions; kein erzwungener Recreate während aktiver Nutzung. Smoke kommt mit dem nächsten regulären `docker compose up -d --force-recreate --no-deps agora` und besteht aus:

  ```bash
  docker compose up -d --force-recreate --no-deps agora
  docker logs -f agora                  # Permission-Errors beobachten
  curl -fsS http://localhost:5001/health
  curl -fsS -H "X-Agora-Token: $AGORA_AUTH_TOKEN" http://localhost:5001/api/status
  # zusätzlich: ein PDF-Upload + Graph-Build (testet logs/, /tmp, uploads/)
  ```

  Falls einer der `cap_add`-Einträge (`CHOWN`, `SETUID`, `SETGID`, `DAC_OVERRIDE`) sich beim Smoke als unnötig erweist, einzeln entfernen und nochmal recyclen. Ziel: minimaler Cap-Set.

## Bekannte Caveats

- Dev-Override (`docker-compose.override.yml`) bind-mountet Repo-Root nach `/app`. Read-only wirkt damit primär auf Pfade außerhalb `/app` (System-Layer); `/app/backend/logs` und `/tmp` werden trotzdem als tmpfs angelegt. In Produktiv-Deployments ohne Override ist die Wirkung umfassender.
- `restart: unless-stopped` greift bei Permission-Fail-Restartloop. Nach Smoke beobachten, ob der Container ohne Restart-Loop bleibt.

## Status

**Done (Patch).** Live-Smoke + Cap-Minimierung als TODO an User, weil aktiver Container nicht unterbrochen wird.
