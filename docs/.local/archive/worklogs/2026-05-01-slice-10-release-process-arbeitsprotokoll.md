# Slice 10 (Repo-Review-Folge, F4): Release-Process-Doku

**Datum:** 2026-05-01
**Branch:** `claude/slice-10-release-process` (Worktree)
**Bezug:** [`docu/2026-05-01-v0.9.0-review-folge-slices-plan.md`](2026-05-01-v0.9.0-review-folge-slices-plan.md), Sub-Slice F4.

## Ziel

Den Release-Pfad als reproduzierbares Rezept festschreiben. Beim
naechsten SemVer-Bump kein Step vergessen, kein Quell-Drift mehr ungesehen.

## Ausgangslage

- F4-Scope laut Plan:
  - `docu/release-process.md` mit allen Versionsquellen, der Reihenfolge
    (CHANGELOG → SemVer-Bump → Sync → Tag → Release-Notes → optional
    Image-Build) und Verweis auf existierende Release-Notes als Vorlage.
- Akzeptanz: Doku liefert reproduzierbares Rezept; `npm run check` gruen.
- Bestand:
  - Sechs Versionsquellen identifiziert: `package.json`,
    `frontend/package.json`, `backend/pyproject.toml`,
    `backend/app/__init__.py`, README-Banner+Status-Block,
    `frontend/src/i18n/locales/{de,en}.json` (`*.version`).
  - **Drift im Repo gefunden**: `backend/pyproject.toml` `0.6.1`,
    `backend/app/__init__.py` `__version__ = "0.8.0"`. Quellen 1, 2, 5
    und 6 stehen alle auf `0.9.0`/`v0.9.0 alpha`.
  - Drei Release-Notes-Dateien als Vorlage (v0.7.0, v0.8.0, v0.9.0).
- Container-Build-Konvention: Multi-Stage `Dockerfile` mit `--target prod`,
  Push nach GHCR (`ghcr.io/arn0ld87/agora`) und Docker-Hub
  (`alexle135/agora-agora`).

## Vorgehen

1. Versionsquellen verifiziert (siehe Ausgangslage).
2. `docu/release-process.md` strukturiert:
   - **Versionsquellen-Tabelle** mit Pfad, Format, Source-of-Truth-
     Hinweis. Drift wird offen benannt — kein Schoenfaerben.
   - **SemVer-Regeln** pre-1.0 inkl. Hinweis, dass MINOR-Bumps Verhalten
     brechen koennen, solange wir <1.0 sind.
   - **Sechs-Stufen-Reihenfolge**: CHANGELOG-Promote, SemVer-Bump in
     allen sechs Quellen mit konkreten `sed`/`npm version`-Snippets,
     Release-Notes-Datei (Strukturblueprint analog v0.9.0), Tag-Sequenz
     (`git tag -a` plus `git push origin main "v$NEW"`), GitHub-Release
     via `gh release create --notes-file`, optional Container-Image-Build
     mit Tags fuer GHCR + Docker-Hub.
   - **Verifikation** mit konkreten Checks (`git ls-remote --tags`,
     `gh release view`, `/api/status.backend.version`-Probe,
     Frontend-Badge-Smoke, post-Tag CI).
   - **Hotfix-Pfad** (Linear-Git, kein Release-Branch).
   - **Tag-Rollback** (destructive, nur vor Veroeffentlichung).
   - **Followups** (Versions-Sync-Slice, optional `scripts/release.sh`).
3. README-Doku-Index (DE + EN) um Zeile `Release-Process: docu/release-process.md` ergaenzt.
4. CHANGELOG `[Unreleased] › Docs` Block oben fuer Slice 10 ergaenzt
   (Konvention aus Slice 7/8/9).
5. Dieses Arbeitsprotokoll geschrieben.
6. `npm run check` als Gate, danach Commit + PR + Merge.

## Geaenderte / neue Dateien

| Datei | Aktion | LOC ca. |
|---|---|---|
| `docu/release-process.md` | neu | 200 |
| `README.md` | edit (DE + EN Doku-Index) | +2 |
| `CHANGELOG.md` | edit (`[Unreleased] › Docs` neuer Slice-10-Block) | +2 |
| `docu/2026-05-01-slice-10-release-process-arbeitsprotokoll.md` | neu | dieses File |

## Verifikation

- `npm run check` — Doku-only-Slice, Bestand stabil.
- Versionsquellen-Tabelle gegen tatsaechlichen Repo-Stand abgeglichen
  (`package.json` 0.9.0, `frontend/package.json` 0.9.0,
  `backend/pyproject.toml` 0.6.1, `backend/app/__init__.py` 0.8.0,
  README v0.9.0, i18n-Locale `v0.9.0 alpha`). Drift wird in der Doku
  benannt, nicht in diesem Slice gefixt — eigenes Sub-Slice (1 Commit
  pro Slice).
- Reihenfolge-Schritte gegen vorhandene Release-Notes-Dateien
  (v0.7.0, v0.8.0, v0.9.0) und Standard-`gh release`-Workflow geprueft.

## Akzeptanzkriterien (laut Plan)

- [x] `docu/release-process.md` existiert.
- [x] Reproduzierbares Rezept (Schritte 1-6 mit konkreten Commands).
- [x] Verweis auf existierende Release-Notes (`docu/2026-05-01-v0.9.0-release-notes.md`).
- [ ] `npm run check` gruen — pending bis zum tatsaechlichen Lauf.

## Issue / Milestone

- F4 ist Folge-Plan, kein offenes GitHub-Issue mit `Closes #N`.
- Repo-Review-Folge ohne Milestone-Counter.

## Followups

- **Versions-Sync** (`backend/pyproject.toml` 0.6.1 → 0.9.0;
  `backend/app/__init__.py` 0.8.0 → 0.9.0). Eigenes Sub-Slice.
- F5 — Test-Coverage-Luecken (SSRF, Upload-Limits, Cypher-Sanitizer;
  einziges Code-Slice im Plan).
- F6 — Branch-Cleanup + README-Update.
