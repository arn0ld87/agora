# Slice 6 (Repo-Review-Umsetzung): Review archivieren + Folge-Sub-Slice-Plan

**Datum:** 2026-05-01
**Branch:** `claude/angry-napier-b3059a` (Worktree)
**Bezug:** Repo-Review aus `claude/v0.9.0-frontend-version` (Commit `e375d42`).

## Ziel

Den externen Repo-Review nicht als „offenen Action Plan“ in main ablegen (PRs 1–5 sind längst umgesetzt), sondern als **Audit-Artefakt** mit klarem Statusblock plus Folge-Plan für die noch offenen Doku-/Test-Punkte.

## Ausgangslage

- `claude/v0.9.0-frontend-version` ist 1 Doku-Commit vor `origin/main`:
  - `e375d42 feat(docs): add repository review and action plan for v0.9.0`
  - Inhalt: `agora_repository_review.md` (Review) + `rolle-du-bist-temporal-otter.md` (Rollenbeschreibung, gehört nicht ins Repo).
- Action-Plan PR 1–5 vollständig in main:
  - Slice 0: `4edf5d3` README-Sync v0.9.0
  - Slice 1 / PR 1: `28a5f2d` Secure Defaults
  - Slice 2 / PR 2: `4bda1d8` Compose Dev/Prod-Trennung
  - Slice 3 / PR 3: `821b4dd` Redis-Tickets
  - Slice 4 / PR 4: `21028d7` CVE-Risk-Register
  - Slice 5 / PR 5: `aace638` Frontend-Token + auth.md
  - Followups: `95cfee6` PR127-Blocker, `9d566b1` Redis-Logging
- PR #119 (v0.9.0 Version-Bump) bereits gemerged.

## Vorgehen

1. Inhalt des Reviews aus `e375d42` extrahiert (`git show origin/claude/v0.9.0-frontend-version:agora_repository_review.md`).
2. Neue archivierte Fassung als `docu/2026-05-01-v0.9.0-repository-review.md` angelegt:
   - **Audit-Header** kennzeichnet das Dokument als historisches Artefakt.
   - **Statusblock** mit Tabelle: Action-Plan-Punkt → Commit-Hash + Commit-Message.
   - **Test-Cross-Check-Tabelle**: Review-Forderung vs. Bestand in `backend/tests/` (12 Zeilen, 7×✅, 1×⚠️, 4×❌/prüfen).
   - **Doku-Cross-Check-Tabelle**: Review-Forderung vs. Bestand in `docu/` (8 Zeilen, 2×✅, 6×❌).
   - **Original-Inhalt unverändert** unterhalb des Statusblocks erhalten.
3. Folge-Plan als `docu/2026-05-01-v0.9.0-review-folge-slices-plan.md` angelegt:
   - 6 Sub-Slices (F1–F6) mit Scope, Akzeptanzkriterien, Aufwand.
   - F1 Deployment-Doku (dev + prod-like).
   - F2 Security-Threat-Model.
   - F3 Operations + Backup/Restore.
   - F4 Release-Process.
   - F5 Test-Lücken (SSRF, Upload, Cypher-Sanitizer, Anonymous-Healthcheck).
   - F6 Branch-Cleanup (`claude/v0.9.0-frontend-version` löschen, README-Doku-Index).
4. `CHANGELOG.md` `[Unreleased] / Docs` erweitert um Slice-6-Eintrag.

## Bewusst nicht übernommen

- `rolle-du-bist-temporal-otter.md` aus dem Quell-Branch — Rollen-/Persona-Beschreibungen gehören nicht ins Projekt-Repo.
- Die Datei `agora_repository_review.md` im Repo-Root — Doku-Artefakte gehören nach `docu/`, nicht in den Root.

## Branch-Strategie

- Nach Merge dieses Sub-Slices in `main` wird `claude/v0.9.0-frontend-version` gelöscht (lokal + remote). Geplant in **Sub-Slice F6**.
- Linearer Git-Flow: dieser Sub-Slice geht direkt gegen `main` (fast-forward, 1 Commit, 1 PR).

## Verifikation

- `npm run check` (Backend-Tests + Frontend-Lint + Build): siehe Commit-Log.
- Manuelle Cross-Checks der Status-/Doku-/Test-Tabellen gegen `git log origin/main` und `ls docu/` / `ls backend/tests/`.

## Issues / Milestone

- Kein Issue für diesen Doku-Sub-Slice (Aufräum-/Archivierungs-Arbeit).
- Folge-Sub-Slices F1–F5 sind Kandidaten für eigene Issues, falls gewünscht.
