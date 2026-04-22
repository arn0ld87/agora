# Changelog

Alle nennenswerten Änderungen an Agora werden hier dokumentiert.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach [SemVer](https://semver.org/lang/de/).

## [Unreleased] — v0.4.0 (in Arbeit)

Scope-Fokus: **Operability & Resilienz**. Details siehe `docs/plan_0.4.md`.

### Geplant
- `GET /api/status` als einheitlicher Ops-Endpoint (Backend, Neo4j, Ollama, Modelle, Disk)
- Strukturiertes JSON-Logging als Opt-in (`AGORA_LOG_FORMAT=text|json`)
- Docker/GPU-Readiness-Detection mit expliziter CPU-Fallback-Doku
- Neo4j-Reconnect bei transienten Laufzeitfehlern
- Python-3.12-Kompat (CAMEL/OASIS): **explizit verschoben** auf v0.4.1/v0.5 — Upstream-blockiert

### Ausführungsplan
- GPU-Detect + `/api/status` → Haiku-Subagent
- Neo4j-Reconnect + Structured-Logging → Sonnet-Subagent
- Beide parallel in isolierten Worktrees, Review durch Hauptagent

## [0.3.1] — 2026-04-22

### Geändert
- **Logo & Favicon**: Agora-Branding auf neues Logo (`media/logo.png`, 1254×1254) umgestellt
  - `frontend/public/icon.png` (Favicon, 256×256)
  - `frontend/src/assets/logo/agora-logo.jpg` (Home-View, 1024×1024)
  - `static/image/agora-logo.jpg` + `agora-logo-source.jpg` (README/Banner-Assets)
  - Commits: `97aca71` → Rebase auf `2dd1e58`

## [0.3.0] — vorher

Siehe Git-Historie vor Einführung dieses Changelogs.
