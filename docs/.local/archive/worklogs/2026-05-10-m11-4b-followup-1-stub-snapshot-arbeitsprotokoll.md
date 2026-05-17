# Arbeitsprotokoll · M11.4b-Followup-1 · Stub-Mode CI-500-Diagnostik + Fix

**Datum:** 2026-05-10
**Branch:** `fix/m11-4b-followup-ci-500`
**Slice-Typ:** CI-Followup auf M11.4b/c
**Subagent:** `agora-frontend-worker` (Sonnet)
**Refs:** Failed Runs `25621119693` (M11.4b), `25621557226` (M11.4c)

## Symptom

Nach Push von M11.4b (`91b7d69`) und M11.4c (`37b9684`) failten die neuen
Smoke-Jobs `Playwright Upload+Graph-Smoke` und `Playwright Minimalreport-Smoke`
in CI mit identischem Fehler:

```
Error: uploadMarkdown: POST /api/graph/ontology/generate fehlgeschlagen (500):
{"code":"internal_error","error":"internal server error","success":false}
   at uploadMarkdown (frontend/tests/e2e/helpers/upload.ts:41)
```

`Health-Smoke` blieb grün — Stack-Hochfahren, Auth, `/healthz`, `/health`,
`/api/status` alles okay. Backend-Container-Logs waren im CI nicht sichtbar,
weil `scripts/e2e-down.sh` Logs nur bei `wait_for`-Timeout dumpte.

## Hypothesen-Triage

| ID | Hypothese | Ergebnis |
|---|---|---|
| H1 | `${AGORA_E2E_LLM_MODE:-}` im e2e-Override exportiert leeren String | **verworfen** — Job-Level-`env:` ist Process-Env, e2e-up.sh appended in `.env`, Override interpoliert korrekt |
| H2 | Stub aktiv, Ontology-Pfad ruft LLM außerhalb von `chat`/`chat_json` | **verworfen** — Stub erreicht `chat_json()` korrekt |
| H3 | Anderer 500-Trigger (Filesystem, Boot-Race, Snapshot-Drift) | **bestätigt** — Snapshot-Datei fehlt im prod-Image |

## Root-Cause

`backend/app/utils/llm_e2e_stub.py:41-44` (Originalcode):

```python
if not _SNAPSHOT_PATH.exists():
    raise ImportError(
        f"Pflichtabschnitt-Snapshot fehlt: {_SNAPSHOT_PATH}\n..."
    )
```

`_SNAPSHOT_PATH` zeigt auf
`/app/backend/tests/eval/snapshots/output-contract-required-sections.txt`.

`Dockerfile:107-130` (prod-Stage) kopiert nur `backend/app` und
`backend/scripts` — `backend/tests/` bleibt aus dem prod-Image draußen
(historisch, weil Tests nicht im Container laufen sollen). Damit fehlt die
Snapshot-Datei im Container.

Ablaufkette im CI:
1. `chat_json()` prüft `AGORA_E2E_LLM_MODE == "stub"` → `True`
2. Lazy-Import `from app.utils.llm_e2e_stub import e2e_stub_response`
3. Beim Import: `_REQUIRED_SECTIONS = _eleven_required_sections()` →
   Datei fehlt → `ImportError`
4. `ImportError` propagiert aus dem lazy-import in `chat_json()` hoch
5. `handle_api_errors` fängt es als generische `Exception`
   → HTTP 500 `{"code":"internal_error",...}`

Der Health-Smoke triggert keinen LLM-Call und ist deshalb grün geblieben.

## Fix (zweischichtig)

### Primär: Snapshot ins prod-Image kopieren

`Dockerfile`: zusätzlicher `COPY` ins prod-Stage:

```dockerfile
COPY --chown=agora:agora backend/tests/eval/snapshots ./backend/tests/eval/snapshots
```

Damit liegt die Datei wieder am erwarteten Pfad.

### Defensive Schicht: Eingebetteter Fallback

`backend/app/utils/llm_e2e_stub.py`:

- `_FALLBACK_REQUIRED_SECTIONS`-Konstante mit den 11 Pflichtabschnitten
  (gespiegelt aus dem Snapshot — Single Source of Truth bleibt die Datei,
  der Fallback ist Notfallnetz).
- `_eleven_required_sections()` wirft kein `ImportError` mehr, sondern
  loggt einen `WARNING` und nutzt den Fallback.
- Modul-Level-Logging beim Import (`AGORA_E2E_LLM_MODE`-Wert + Section-Anzahl)
  — taucht ab sofort in den Container-Logs auf.

Damit bleibt der Stub-Pfad funktional, auch wenn ein zukünftiges Refactor
den `COPY` wieder rauswirft. Der Snapshot-Drift-Schutz aus M11.8b läuft
weiterhin über `tests/eval/`, nicht über die Image-Kopie.

## Diagnostik (für nächste CI-Failures)

`frontend/tests/e2e/global-teardown.ts`:
- Neue Funktion `dumpContainerLogs()` — dumpt `docker compose logs` für
  `agora` (tail=500), `agora-neo4j` (tail=200), `agora-redis` (tail=100)
  vor `e2e-down.sh`.
- Bedingung: `process.env.CI` gesetzt. Im Erfolgsfall etwas Lärm im
  CI-Log, dafür ab sofort vollständige Diagnose bei Failures.

`frontend/tests/e2e/helpers/diagnostics.ts` (neu):
- `assertStubModeActive(apiCtx, baseURL)` — `GET /api/status` + Console-Log
  mit Backend-Health und Stub-Mode-Status. Kein hartes Assert, nur
  Diagnose-Output.

`upload-graph.spec.ts` und `minimal-report.spec.ts`: rufen
`assertStubModeActive` vor dem ersten API-Call auf.

## Verifikation (lokal, im Worktree)

| Schritt | Ergebnis |
|---|---|
| `npm run lint` | grün |
| `npm run typecheck` | grün |
| `npx playwright test --list` | 6 Tests in 3 Files erkannt |
| `npm test -- --run` | 461 passed |
| `uv run ruff check app/ tests/` | All checks passed |
| `uv run mypy app` | 132 source files, no issues |
| `uv run pytest -x -q -m "not llm"` | 1681 passed, 9 skipped |
| `tests/test_llm_e2e_stub.py` | 12 passed (keine Regression) |
| `tests/contracts/` | 88 passed |
| `git diff --exit-code schemas/` | clean |
| Stub-Import mit `AGORA_E2E_LLM_MODE=stub` | 11 Sections geladen, Logger-Output sichtbar |

## Geänderte Files

- `Dockerfile` (+5 Zeilen, 1 zusätzliches COPY mit Begründungs-Kommentar)
- `backend/app/utils/llm_e2e_stub.py` (Fallback-Konstante + Soft-Fail in
  `_eleven_required_sections`, Modul-Level-Import-Log)
- `frontend/tests/e2e/global-teardown.ts` (Container-Log-Dump bei CI)
- `frontend/tests/e2e/helpers/diagnostics.ts` (neu, ~30 LOC)
- `frontend/tests/e2e/upload-graph.spec.ts` (Diagnostik-Aufruf)
- `frontend/tests/e2e/minimal-report.spec.ts` (Diagnostik-Aufruf)
- `docu/2026-05-10-m11-4b-followup-1-stub-snapshot-arbeitsprotokoll.md`
- `CHANGELOG.md` `[Unreleased] ### Fixed`

## Erwartung

Nach Push wird `e2e-smokes::upload-graph-smoke` und `::minimal-report-smoke`
grün — primär durch den Dockerfile-Fix, sekundär abgesichert durch den
Fallback. Wenn doch noch was failt, sind die Container-Logs ab sofort im
CI-Log lesbar und die Diagnose dauert keine Stunde mehr.
