# M11.4a-Followup #8 — Arbeitsprotokoll

**Datum:** 2026-05-09  
**Branch:** `fix/m11-4a-followup-8-ci-rot`  
**Basis:** `origin/main` 7f4f609 (post-M11.8c)  
**Author:** Orchestrator (Opus) nach Codex-Diagnose

## Auslöser

Auf `main` 8a79548 (M11.4a-Followup #7) waren zwei CI-Checks rot:

| Check | CI-Run | Failure |
|---|---|---|
| Backend tests + lint | [25595884772](https://github.com/arn0ld87/agora/actions/runs/25595884772) | `tests/test_event_bus.py::test_request_response_correlation[FilePollingEventBus]` — TimeoutError nach 2.0 s |
| Playwright Health-Smoke | [25595884785](https://github.com/arn0ld87/agora/actions/runs/25595884785) | `PermissionError: '/app/backend/app/../uploads/run_registry'` beim Backend-Boot |

## Bug 1 — test_event_bus Race

### Diagnose

`bus.subscribe(..., timeout=2.0, poll_interval=0.05)` ergibt rechnerisch
40 Poll-Zyklen. Auf Shared-Filesystem-CI-Runnern reicht das nicht
zuverlässig — der Failing-Run zeigt eine korrekt gesetzte
`correlation_id`, aber die Response-Datei wird nicht innerhalb des
Fensters sichtbar. Lokale Reproduktion (5× hintereinander) bleibt grün:
keine echte Race-Condition, sondern CI-Timing.

### Fix

`backend/tests/test_event_bus.py::test_request_response_correlation`:
- `timeout=2.0` → `timeout=5.0` (responder-subscribe und
  request_response-call)
- `t.join(timeout=3.0)` → `t.join(timeout=6.0)`
- Docstring um Begründung erweitert (CI-Run-Verweis)

5.0 s = ~100 Poll-Zyklen, deutlich über jedem realistischen IO-Stau.
Andere `timeout=2.0`-Stellen in der Datei gehören zu anderen Tests und
zu `t.join`-Timeouts; bewusst nicht angefasst.

### Verify

```
backend/tests/test_event_bus.py 13 passed in 2.72s
```

## Bug 2 — PermissionError `/app/backend/uploads/run_registry`

### Diagnose

`docker-compose.yml` mountet `./backend/uploads:/app/backend/uploads` als
Bind-Mount. Auf einem fresh CI-Checkout existiert das Source-Verzeichnis
nicht — der Docker-Daemon legt es beim ersten `docker compose up`
implizit als `root:root` an. Der Container-User ist `agora` (UID 1000,
siehe `Dockerfile:127`), kann nicht reinschreiben.

`RunRegistry.__new__` ruft beim Boot `os.makedirs(REGISTRY_DIR,
exist_ok=True)` mit `REGISTRY_DIR=/app/backend/app/../uploads/run_registry`
— scheitert mit PermissionError, gunicorn-Worker exit code 3.

Followup #7 hat `read_only: false` im E2E-Override gesetzt — das deckt
einen anderen Failure-Modus (Container-FS readonly), nicht das
Bind-Mount-Source-Permission-Problem.

### Fix

`scripts/e2e-up.sh` (vor `docker compose up`):

```bash
mkdir -p "${REPO_ROOT}/backend/uploads/run_registry" "${REPO_ROOT}/backend/uploads/simulations"
if [[ "$(id -u)" == "0" ]]; then
  chown -R 1000:1000 "${REPO_ROOT}/backend/uploads"
else
  chmod -R 0777 "${REPO_ROOT}/backend/uploads"
fi
```

CI-Runner-Variante (`id == 0`) chownt explizit auf Container-User-UID;
lokale Dev-Maschinen (`id != 0`) gehen den robusteren `chmod 0777`-Weg
(Bind-Mount-Source gehört Dev-User, der Container-User ist eine andere
UID — chmod ist die einzige saubere Lösung ohne sudo).

`docker-compose.e2e.override.yml`-Kommentar erweitert um Followup-#8-
Begründung. tmpfs-Mount für `/app/backend/uploads` wurde **nicht**
ergänzt, weil er mit dem Bind-Mount aus `docker-compose.yml` kollidiert
(Compose-Fehler: `target /app/backend/uploads already mounted as
services.agora.volumes`).

### Verify

Lokaler Docker-Smoke konnte nicht ausgeführt werden (Sandbox).
Compose-Config-Merge mit Stub-Env:

```
NEO4J_PASSWORD=ci-test SECRET_KEY=ci-test AGORA_AUTH_TOKEN=ci-test \
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f deploy/compose/docker-compose.prod-with-proxy.yml \
  -f deploy/compose/docker-compose.e2e.override.yml config
→ kein Mount-Konflikt mehr (vorheriger Versuch mit tmpfs failed)
```

Verifikation gegen den nächsten CI-Run.

## Geänderte Dateien

- `backend/tests/test_event_bus.py` — Timeout 2.0→5.0 in
  test_request_response_correlation
- `scripts/e2e-up.sh` — mkdir+chown/chmod für `backend/uploads/`
  Bind-Mount-Source
- `deploy/compose/docker-compose.e2e.override.yml` — Kommentar erweitert
  (kein Funktions-Diff zur Followup-#7-Version)
- `CHANGELOG.md` — Fixed-Eintrag
- `docs/2026-05-09-m11-4a-followup-8-arbeitsprotokoll.md` — dieses
  Protokoll

## Zustand der Codex-Diagnose

Codex hatte Bug 1 korrekt diagnostiziert (CI-Timing, kein Race) und Bug
2 korrekt lokalisiert (Bind-Mount + Container-User), aber den Fix für
Bug 2 als tmpfs-Mount vorgeschlagen — der scheitert am
Bind-Mount-Konflikt. Außerdem hatte Codex die Edits nicht in den
Worktree persistiert, der Bericht stimmte nicht mit dem Filesystem-State
überein. Orchestrator hat danach selbst gefixt.

## Folge-Slices

- `fix/m11-4a-followup-9` falls auch nach diesem Fix noch CI-Rot
  bleibt — dann tieferer Einstieg in Compose-Override-Reihenfolge
- Tracking-Issue für `tests/test_event_bus.py` Timeout-Heuristik (alle
  IPC-Tests sollten denselben CI-tauglichen Wert nutzen)
