# Sub-Slice 44 — F5 Doku-Sync (M9 #1) — Arbeitsprotokoll

## Ziel

Einen Single Source of Truth für Test-Counts und Versionsstände etablieren. Inline-Zahlen aus README.md und CLAUDE.md entfernen, ROADMAP auf v0.9.0+ / 2026-05-03 abheben, CONTRIBUTING.md am Repo-Root neu anlegen.

## Befund vor dem Slice

Drei kritische Drift-Probleme:

1. **Test-Count-Widerspruch:**
   - `README.md` Z. 11 + Z. 65: „**1383 Tests grün** (1258 Backend + 125 Frontend)"
   - `CLAUDE.md` Z. 7: „Backend 1289 Tests, Frontend 141 Tests" (= 1430 Tests, nicht 1383)
   - Aktueller Zustand (verifiziert via `uv run pytest --collect-only -q`): **Backend 1330 collected, Frontend 17 Spec-Files** (die Frontend-Doku-Zahlen waren Test-Cases-Schätzungen, keine Datei-Counts — siehe Hinweis in STATUS.md).
   - Ursache: README spiegelt ältere Zahlen, CLAUDE.md wurde nicht aktualisiert, keine Single Source of Truth existiert.

2. **ROADMAP veraltet:**
   - Header: „Stand: 2026-04-27" (6 Tage alt zum Slice-Datum).
   - Inhalt: „Current State (v0.6.1)" (drei Minor-Versionen unter aktueller v0.9.0+).
   - Implementierungs-Drift: Layer 0–5 sind längst grün, ROADMAP erzählte aber noch von v0.5/v0.6-Erzeugnissen.
   - Keine Übersicht der aktuellen Milestones (M9–M13).

3. **CONTRIBUTING.md fehlt komplett:**
   - Repo hatte keine Datei, die erklärt, welche Dokumentation wofür existiert.
   - Branch-Hygiene und Quality-Gates waren nur in CLAUDE.md dokumentiert (Agent-Fokus).
   - Neue Contributors finden nicht schnell heraus, wo Sub-Slice-Einträge hingehören oder wie die Doku-Struktur aufgebaut ist.

## Geänderte Dateien

| Datei | Aktion | Begründung |
|---|---|---|
| `docu/STATUS.md` | Neu angelegt | Single Source of Truth für Versionsstände (0.9.0 Backend/Frontend/Root) und Test-Counts (1330 Backend collected, 17 Frontend Spec-Files) plus Layer-Status und Milestone-M9-Verweis |
| `scripts/sync-status.sh` | Neu angelegt, ausführbar | Bash-Script für automatisierte Re-Generierung von STATUS.md; extrahiert Versionen aus pyproject.toml / package.json, Backend-Count via `uv run pytest --collect-only -q` (timeout 180 s), Frontend-Spec-Files via `find`; `--check`-Modus für CI-Drift-Detection |
| `README.md` Z. 11 | Editiert | „**1383 Tests grün** (1258 Backend + 125 Frontend)" → „Aktuelle Test-Counts: [`docu/STATUS.md`](docu/STATUS.md)." |
| `README.md` Z. 65 | Editiert | „(**1258 Backend + 125 Frontend Tests** = 1383 grün, ...)" → „(Test-Counts in [`docu/STATUS.md`](docu/STATUS.md); ...)" |
| `CLAUDE.md` Z. 7 | Editiert | „Status: v0.9.0+, Backend 1289 Tests, Frontend 141 Tests, ..." → „Status: v0.9.0+ post-tag · Layer 0–6 grün · Layer 7–10 in Arbeit · Test-Counts: [`docu/STATUS.md`](docu/STATUS.md)." |
| `docu/ROADMAP.md` Header | Editiert | Stand auf 2026-05-03, Header-Verweise auf STATUS.md / CLAUDE.md / PLAN.md, „v0.6.1" → „v0.9.0+ post-tag, Layer 0–6 grün". 0.5/0.6-Linien-Beschreibung in expliziten `## Historie (0.5 / 0.6)`-Block verschoben |
| `docu/ROADMAP.md` Now/Next/Later | Eingefügt | Neuer Block mit M9 (F1–F5 Prod-Hardening, Slices 44–48), M10 (Test-Schärfe, Slices 49–52), M11–M13 (Code-Hotspots + Feature-Welle + v1.0-Vorbereitung) — ersetzt vage v0.7/v0.8-Ziele durch operative Slice-Nummern |
| `CONTRIBUTING.md` | Neu angelegt | Übersicht Datei-Rollen (CLAUDE.md, PLAN.md, STATUS.md, ROADMAP.md, Glossar, CHANGELOG, docu/decisions/, docu/history/), Branch-Hygiene, Quality-Gates-Snippet, Sub-Slice-Workflow-Erklärung, Verweis auf Wording-Glossar |
| `CHANGELOG.md` `[Unreleased]` | Editiert | Sub-Slice-44-Eintrag in `### Documentation` mit Verweis auf alle geänderten Dateien und dieses Arbeitsprotokoll |
| `docu/2026-05-03-slice-44-doku-sync-arbeitsprotokoll.md` | Neu angelegt | Dieses Protokoll |

## Akzeptanz-Checks

1. **Inline-Zahlen entfernt:**
   ```bash
   rg -n '1383 Tests|1258 Backend|125 Frontend|1289 Tests|141 Tests' README.md CLAUDE.md
   # Ergebnis: leer (kein Match)
   ```

2. **ROADMAP-Eingangsbereich frei von alten Stand-Markern:**
   ```bash
   head -15 docu/ROADMAP.md | grep -E 'v0\.6\.1|2026-04-27'
   # Ergebnis: leer (kein Match — die 0.5/0.6-Linien-Erwähnung steht jetzt in `## Historie (0.5 / 0.6)`)
   ```

3. **STATUS.md existiert und ist idempotent:**
   ```bash
   ls -la docu/STATUS.md
   bash scripts/sync-status.sh
   bash scripts/sync-status.sh --check   # exit 0
   ```

4. **CONTRIBUTING.md am Repo-Root vorhanden:**
   ```bash
   ls -la CONTRIBUTING.md
   grep -c "## Welche Datei wofür" CONTRIBUTING.md   # ≥ 1
   ```

5. **`scripts/sync-status.sh` ist ausführbar:**
   ```bash
   ls -la scripts/sync-status.sh | grep -E '^-rwx'
   ```

6. **Schemas nicht angetastet:**
   ```bash
   git diff --exit-code schemas/   # exit 0
   ```

7. **Sanity Backend-Tests (nur Regression-Check, kein Code geändert):**
   ```bash
   cd backend && uv run pytest -x -q --maxfail=1
   # Ergebnis: 1323 passed, 9 skipped (Redis ohne TEST_REDIS_URL + Compose-Snapshot ohne .env)
   ```

## Folge-Slices

- **Sub-Slice 45 (F1):** Reverse-Proxy-Konfiguration (nginx / HAProxy vor Prod-Container, Issue #106).
- **Sub-Slice 46–47 (F2):** Auth-Hardening (Signed-Ticket-API, Frontend-Migration, Redis-Session-Store).
- **Sub-Slice 48 (F3):** Gunicorn-Gevent-Worker-Modell (Fork-Safety-Tests).

Alle Milestone M9, aufbauend auf dieser Doku-Stabilisierung.

## Caveat / Slice-Nummern-Kollision

Während dieses Slice in einem Worktree gearbeitet wurde, ist parallel der mypy-Tooling-Slice auf `origin/main` gemerged worden — der trägt im CHANGELOG ebenfalls die Bezeichnung „Sub-Slice 43". Um Verwechslungen zu vermeiden, ist dieser Doku-Sync auf **Sub-Slice 44** umnummeriert worden, alle nachfolgenden Slice-Nummern in der ROADMAP entsprechend +1.

`scripts/sync-status.sh --check` ist noch nicht in die CI-Pipeline verdrahtet (würde als Drift-Gate vor jedem Merge laufen). Das ist Scope für M10 (F6 Coverage / F12 Lint-Tiefe). Derzeit manuell aufzurufen.
