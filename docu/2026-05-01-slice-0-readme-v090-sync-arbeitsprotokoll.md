# Slice 0 — README & Doku-Sync auf v0.9.0

**Datum:** 2026-05-01
**Branch:** `claude/sleepy-torvalds-32f68f`
**Slice-Quelle:** Repo-Review-Umsetzung Slice 0 (vor PR1–PR5)

## Ziel

README und Changelog mit dem Repo-Stand v0.9.0 in Deckung bringen. Nur Doku-Edits, keine Code-Logik. Diskrepanz zwischen Schnellstart-Doku und tatsächlichem Compose-Verhalten transparent markieren — der Fix kommt in Slice 2 (PR2).

## Ausgangslage

- `package.json` steht auf `0.9.0` (Beleg: [package.json:3](../package.json:3)).
- Release-Notes liegen unter [docu/2026-05-01-v0.9.0-release-notes.md](2026-05-01-v0.9.0-release-notes.md), Milestone „Domain Cleanup" mit 12/12 Issues, 671 Backend + 40 Frontend = 711 Tests.
- README behauptete bis hierher v0.8.0 mit 519 Tests (488 Backend + 31 Frontend) — gleicher Release-Tag (2026-05-01), aber ältere Version.
- `docker-compose.yml` setzt **kein** `target: dev`; das Multi-Stage-Dockerfile defaultet damit auf den `prod`-Stage (gunicorn). Frontend/Backend-Ports binden `0.0.0.0`, Neo4j-Browser/Bolt ebenfalls — wird in Slice 2 (PR2) entschärft.
- `[Unreleased]`-Block in `CHANGELOG.md` war leer.

## Änderungen

### README.md

- Status-Header (Z. 11): `v0.8.0 released` → `v0.9.0 released`; Test-Counter `519 (488/31)` → `711 (671/40)`; Release-Notes-Link auf v0.9.0; Vorgänger-Link auf v0.8.0; Issue-Counter „13/13" → „12/12 (Milestone Domain Cleanup)".
- Status-Block (Z. 24, deutsche Sektion / Z. 345, englische Sektion): `v0.8.0` → `v0.9.0`.
- Engineering-Stand-Überschrift (Z. 54 / Z. 362): `v0.8.0` → `v0.9.0`.
- Quality-Gate-Bullet: Testzahlen 488/31 → 671/40, „+192 ggü. v0.8.0" angemerkt.
- Zwei neue Bullets pro Sprache zu v0.9.0-Schwerpunkten: Domain-Cleanup-Reduktionen (`simulation_manager.py` −49 %, `report_agent.py` −31,6 %, `neo4j_storage.py` −82,7 %), neue `services/`-Schichten, fünf-Modul-Storage-Split; Wire-Identity-Pin (`models/graph.py`, Issue #52); FSM-Aktivierung (Issue #42, `ALLOWED_TRANSITIONS` als Single-Source-of-Truth, `InvalidStatusTransition`).
- Schnellstart unter „Option A: Docker Compose": Hardening-Drift-Block direkt nach `docker compose up -d` eingefügt — listet die drei bekannten Drifts (`target` fehlt, Neo4j auf 0.0.0.0, Backend/Vite auf 0.0.0.0). Slice 2 entschärft das.

### CHANGELOG.md

- `[Unreleased] → ### Docs`-Block angelegt mit Slice-0-Eintrag (Test-Counter-Sync, Engineering-Stand-Refresh, Schnellstart-Drift-Hinweis, Verweis auf dieses Arbeitsprotokoll).

## Tests

Reine Doku-Änderung; keine neuen Tests.

Akzeptanz-Greps:

```
$ grep -n "v0.8.0\\|v0\\.8" README.md
11:> **v0.9.0 released:** ... Vorgänger: [v0.8.0](docu/2026-05-01-v0.8.0-release-notes.md).
56:- 671 Backend + 40 Frontend Tests (+192 ggü. v0.8.0)
372:- 671 backend + 40 frontend tests (+192 vs. v0.8.0)
```

→ alle verbleibenden Treffer sind Vorgänger-Verweise / Vergleichswerte. Keine Status-Aussage mehr auf v0.8.0.

`npm run check` läuft als Quality-Gate vor dem Slice-0-Commit; bei rot → STOP und Reporting an User.

## Risiken

- Wenn der User die `agora-teaser.gif`/Demo-Sektion separat tracked, ist sie hier unverändert — Slice 0 fasst nur die statischen Status-/Engineering-/Schnellstart-Blöcke an.
- Schnellstart-Drift-Block macht die Doku ehrlicher, aber der Erstkontakt-Eindruck wird aktuell schlechter. Slice 2 behebt das innerhalb des nächsten Commits.

## Open Questions

- Soll `docu/v1-development-log.md` einen Slice-0-Eintrag bekommen? Aktuell nicht — diese Datei ist v1.0-API-Contract-spezifisch (Auth-Envelope, dict-Returns, 404/405-Handler) und Doku-Sync passt thematisch nicht. Falls gewünscht, separat nachziehen.

## Rollback

`git revert <Slice-0-SHA>` stellt README und CHANGELOG-`[Unreleased]`-Block wieder her. Keine schema/Code-Migrationen, keine Datenwirkung.
