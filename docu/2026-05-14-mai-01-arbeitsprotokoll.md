# Arbeitsprotokoll MAI-01 — P4.4 Mode-Smokes in CI verdrahten

**Slice-ID:** MAI-01
**Titel:** P4.4 Report-Mode-Smokes als vierter Job in e2e-smokes.yml
**Implementer:** Sonnet via agora-frontend-worker (claude-sonnet-4-6)
**Datum:** 2026-05-14
**Branch:** `feat/mai-01-mode-smokes-ci`
**Worktree:** `/Volumes/T7/Projekte/agora-worktrees/mai-01/`

---

## Ausgangslage

`frontend/tests/e2e/report-modes.spec.ts` war bereits implementiert (P4.4-Spec für
strict/balanced/explorative-Modi), wurde aber von keinem CI-Job ausgeführt. Der vierte
Smoke-Job fehlte in `.github/workflows/e2e-smokes.yml`.

Status-Check ergab: `report-modes-smoke`-Job war im Worktree bereits eingetragen —
der Worktree befand sich in vollständigem Zustand (git status zeigte beide Dateien als
modified, d.h. Änderungen waren bereits vorgenommen).

---

## Änderungs-Liste

| Datei | Delta | Beschreibung |
|---|---|---|
| `.github/workflows/e2e-smokes.yml` | +48 Zeilen | `report-modes-smoke`-Job nach `minimal-report-smoke` ergänzt |
| `CHANGELOG.md` | +1 Zeile | MAI-01-Eintrag in `[Unreleased]`-Sektion |
| `docu/2026-05-14-mai-01-arbeitsprotokoll.md` | neu | dieses Protokoll |

---

## Neuer Job-Block (Zusammenfassung)

Job `report-modes-smoke` in `e2e-smokes.yml`:
- `timeout-minutes: 30` (25 % mehr als minimal-report wegen 3 Modi × Report-Polling)
- `AGORA_E2E_LLM_MODE: 'stub'` — deterministisch, kein Ollama nötig
- `AGORA_SKIP_EMBEDDING_PROBE: 'true'` — analog allen anderen Smoke-Jobs
- Playwright-Aufruf: `npx playwright test report-modes.spec.ts --reporter=list,github`
- Trace-Artefakt bei Failure: `playwright-trace-report-modes` (14 Tage Retention)

Der `paths`-Filter im `on.pull_request`-Block deckt `frontend/tests/e2e/**` bereits ab —
kein Änderungsbedarf (Schritt 3 des Briefs bestätigt).

---

## Verify-Output (Akzeptanz-Checks)

```
# Check 1: Genau 4 Smoke-Jobs
grep -E "^  [a-z-]+-smoke:" .github/workflows/e2e-smokes.yml | wc -l
→ 4  ✓

# Check 2: Job vorhanden
rg -n "report-modes-smoke:" .github/workflows/e2e-smokes.yml
→ 202:  report-modes-smoke:  ✓

# Check 3: Syntax-Validierung
npx --yes @action-validator/cli@latest .github/workflows/e2e-smokes.yml
→ WARNING: Glob validation is not yet supported. Glob at /on/pull_request/paths will not be validated.
→ (keine Fehler — Glob-Warning ist bekannt und betrifft alle Smoke-Jobs gleichwertig)  ✓
```

---

## Git-Status (nicht-committeter Working-Tree)

```
 M .github/workflows/e2e-smokes.yml
 M CHANGELOG.md
?? docu/2026-05-14-mai-01-arbeitsprotokoll.md
```

---

## Folge-Slices

Laut `docu/plan.mai.md` Block A folgt als nächster:

**MAI-04** — Schema-Drift-Gate `--check`
- Files: `backend/app/contracts/dump_schemas.py`, `.github/workflows/contract-gates.yml`
- Refs: R12 (Contract-Generation + Status-Sync)
