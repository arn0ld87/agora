# Slice 9 (Repo-Review-Folge, F3): Operations + Backup/Restore

**Datum:** 2026-05-01
**Branch:** `claude/slice-9-ops-backup` (Worktree)
**Bezug:** [`docs/2026-05-01-v0.9.0-review-folge-slices-plan.md`](2026-05-01-v0.9.0-review-folge-slices-plan.md), Sub-Slice F3.

## Ziel

Ops-Wissen und Backup-Strategie aus Tribal-Knowledge in Repo-Doku heben.
Eine Stelle, wo „was tun, wenn Neo4j down ist?" und „wie restore ich
einen Dump?" greifbar sind. Single-User-Setup, kein SLA — aber das
Future-Alex-um-02:30-Problem.

## Ausgangslage

- F3-Scope laut Plan:
  - `docs/operations.md`: Logs, Healthchecks, Ressourcenbedarf, Ausfaelle.
  - `docs/backup-restore.md`: Neo4j-Dump, Uploads, Reports, Cron,
    Restore-Drill.
- Akzeptanz: beide Dateien existieren, README/Operations-Sektion
  verlinkt; `npm run check` gruen.
- Code-Stand:
  - `/health` (public, Liveness) in `backend/app/__init__.py:200`.
  - `/api/status` (aggregiert, Backend/Neo4j/Ollama/Disk/GPU + Timestamp)
    in `backend/app/api/status.py:130`. GPU-Probe via Ollama REST `/api/ps`.
  - Logger: `RotatingFileHandler` 10 MB / 5 Backups in
    `backend/app/utils/logger.py:234`, `LOG_DIR = backend/logs/`,
    `AGORA_LOG_FORMAT={text,json}`.
  - `signed_ticket.consume()` faellt auf in-process zurueck wenn Redis
    down (Slice 3 PR3).
  - Compose: tmpfs `/app/backend/logs` (64 MB), Neo4j-Memory
    Pagecache 4g + Heap 2g, `redis_data`/`neo4j_data`/`neo4j_logs`
    Named Volumes, Bind-Mounts `./backend/uploads` und
    `./backend/.cache/huggingface`.

## Vorgehen

1. Snapshot der relevanten Code-Pfade (auth, status, logger,
   signed_ticket, simulation_runner Subprocess-Surface,
   docker-compose-Volumes) damit die Doku den realen Code spiegelt.
2. `docs/operations.md` strukturiert:
   - **Healthchecks** mit Beispiel-Response und Mapping „rotes Feld → was
     pruefen?".
   - **Logs**: Quellen-Tabelle (Logger / Console / Gunicorn / Vite /
     Neo4j / OASIS), Konfig-Tabelle (`AGORA_LOG_FORMAT`, `LOG_DIR`,
     Rotation), Redaction-Reichweite (`agora.*`, nicht `print()`),
     Cheat-Sheet wichtiger Log-Marker.
   - **Ressourcenbedarf**: RAM/CPU pro Komponente Idle vs. Last,
     Disk-Bedarf der Volumes, GPU-Probe.
   - **Ausfaelle**: sechs Szenarien (Neo4j down, Redis down, Ollama
     down, Backend 5xx-Schwarm, Disk voll, Container-Restart-Loop) mit
     Symptom / Diagnose-Befehlen / Ursachenliste / Fallback.
   - **Routine-Aufgaben** (Update, Dependency, Backup, Drill,
     `.env`-Rotation, Log-Volumen).
3. `docs/backup-restore.md` strukturiert:
   - Asset-Tabelle mit Restore-Verlust-Akzeptanz.
   - Neo4j-Online-Dump-Sequenz (`neo4j-admin server stop` → `dump` →
     `cp` → `start`); Btrfs-Volume-Snapshot als schnelle Variante.
   - Restore-Pfad mit Pre-Wipe (`rm -rf /data/databases/neo4j`) und
     Cypher-Smoke-Test.
   - Restore-Drill als Quartals-Pflicht.
   - Filesystem-Artefakte via Restic / Borg / Btrfs;
     `.env`-Sonderbehandlung (Passwort-Manager statt Repo).
   - Cron-Strategie (Neo4j taeglich 03:00, Restic stuendlich, Forget
     woechentlich) plus Retention-Vorschlag.
   - Worst-Case-Recovery-Reihenfolge.
   - Was bewusst nicht gesichert wird (Redis, HF-Cache, tmpfs).
4. README-Doku-Index (DE + EN) um neue Zeile `Operations:
   docs/operations.md · docs/backup-restore.md` ergaenzt; gleichzeitig
   `security-threat-model.md` (Slice 8) in die Auth-/Security-Zeile
   eingehaengt — war noch ueber.
5. CHANGELOG `[Unreleased] › Docs` Block fuer Slice 9 oben ergaenzt
   (Konvention aus Slice 7/8).
6. Dieses Arbeitsprotokoll geschrieben.
7. `npm run check` als Gate, danach Commit + PR + Merge.

## Geaenderte / neue Dateien

| Datei | Aktion | LOC ca. |
|---|---|---|
| `docs/operations.md` | neu | 220 |
| `docs/backup-restore.md` | neu | 200 |
| `README.md` | edit (DE + EN Doku-Index) | +4 / -2 |
| `CHANGELOG.md` | edit (`[Unreleased] › Docs` neuer Slice-9-Block) | +2 |
| `docs/2026-05-01-slice-9-ops-backup-arbeitsprotokoll.md` | neu | dieses File |

## Verifikation

- `npm run check` — Doku-only-Slice darf den Gate nicht roetlich faerben.
- Inhalts-Konsistenz mit Code:
  - `/health` und `/api/status` Schema gegen `backend/app/__init__.py`,
    `backend/app/api/status.py`.
  - Logger-Rotation (10 MB / 5 Backups, `LOG_DIR`, `AGORA_LOG_FORMAT`)
    gegen `backend/app/utils/logger.py`.
  - Compose-Volumes/tmpfs gegen `docker-compose.yml`.
  - Neo4j-Memory-Settings (Pagecache 4g, Heap 2g) gegen Compose.
  - Signed-Ticket-Fallback gegen `backend/app/utils/signed_ticket.py`.

## Akzeptanzkriterien (laut Plan)

- [x] `docs/operations.md` existiert mit Logs / Healthcheck / Ressourcen
      / Ausfaellen.
- [x] `docs/backup-restore.md` existiert mit Neo4j-Dump / Uploads /
      Reports / Cron / Drill.
- [x] README/Operations-Sektion verlinkt beide Dateien (DE + EN).
- [ ] `npm run check` gruen — pending bis zum tatsaechlichen Lauf.

## Issue / Milestone

- F3 ist Folge-Plan, kein offenes GitHub-Issue mit `Closes #N`.
- Repo-Review-Folge ohne Milestone-Counter.

## Followups

- F4 — Release-Process.
- F5 — Test-Coverage-Luecken (SSRF, Upload, Cypher-Sanitizer; einziges
  Code-Slice im Plan).
- F6 — Branch-Cleanup + README-Update.
