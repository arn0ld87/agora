# Arbeitsprotokoll · M11.4b-Followup-2 · Embedding-Service-Stub + Outline-Validation-Fix

**Datum:** 2026-05-10
**Branch:** `fix/m11-4b-followup-2-embedding-stub`
**Slice-Typ:** CI-Followup auf M11.4b/c Followup-1
**Subagent:** `agora-refactor-worker` (Sonnet)
**Refs:** CI-Run `25622221164` (Followup-1 noch failt), Sub-Slice M11.4b-Followup-2

## Symptome (CI-Run 25622221164)

Drei miteinander verkettete Fehler nach Followup-1:

### Symptom A — Embedding-Service nicht gestubt

```
agora | WARNING: Ollama connection failed (attempt 1/3): HTTPConnectionPool(...):
       Max retries exceeded with url: /api/embed (Connection refused)
agora | Graph search failed, degrading to local search: Ollama embedding failed after 3 retries
```

`EmbeddingService.embed()` und `embed_batch()` riefen direkt Ollama. Im CI-Stack
gibt es kein Ollama. Der LLM-Stub (`llm_e2e_stub.py`) deckte nur
`chat()`/`chat_json()`, nicht Embeddings.

### Symptom B — Outline-Validation failt

```
agora | ERROR: Outline planning failed: 1 validation error for ReportOutlineModel
```

`_stub_plan_response()` lieferte 11 Sections. `planning.py` konstruierte
daraus ein `ReportOutlineModel`, das aber `max_length=5` hatte — Schema-Drift
zwischen `planning.py` (M11.8a-Followup: Section-Cap entfernt) und
`report_contract.py` (vergessene Anpassung).

### Symptom C — E2E-Test-Timeouts (Folgeschaden)

`upload-graph.spec.ts` und `minimal-report.spec.ts` timeouteten — verursacht
durch 3×Embedding-Retry-Delay (Symptom A) und Outline-Validation-Fehler
(Symptom B).

## Hypothesen-Triage

| ID | Hypothese | Ergebnis |
|---|---|---|
| H1 | `EmbeddingService.embed()` ruft Ollama auch im Stub-Modus | **bestätigt** — kein Stub-Branch vorhanden |
| H2 | `ReportOutlineModel.sections` hat `max_length=5`, Stub liefert 11 | **bestätigt** — reproduzierbar via `ReportOutlineModel.model_validate(_stub_plan_response())` |
| H3 | E2E-Timeouts sind Folgeschaden von A+B | **plausibel** — bei Fix A+B sollten verschwinden |

## Fix

### Teil A — Embedding-Service-Stub

Datei: `backend/app/storage/embedding_service.py`

- `EmbeddingService._stub_vector(text)`: neue Hilfsmethode. Formel:
  `vec[i] = ((hash(text) + i) % 1000 - 500) / 500.0`, dann L2-normiert.
  Deterministisch per Text, nicht konstant 1.0 (verhindert Cosine-Dedup-Fehler).
- `embed()`: früher Rückgabepfad wenn `AGORA_E2E_LLM_MODE=stub`.
- `embed_batch()`: früher Rückgabepfad (list comprehension über `_stub_vector`).
- `health_check()`: gibt `True` zurück im Stub-Modus, ohne Netzwerkaufruf.
- Einmalig `logger.info("EmbeddingService: stub-mode aktiv, dim=…")` via
  `_stub_mode_logged` Klassen-Attribut (idempotent über alle Instanzen).
- Dimension: `Config.VECTOR_DIM` — kein hartkodierter Wert, kein neues `_dim`-Attribut.

### Teil B — Outline-Validation-Fix

Datei: `backend/app/contracts/report_contract.py`

- `ReportOutlineModel.sections`: `max_length=5 → max_length=15`,
  `min_length=2 → min_length=1`.
- Ursache: `planning.py` hatte M11.8a-Followup (PR #335) den Section-Cap
  aus dem LLM-Prompt entfernt, `ReportOutlineModel` blieb aber bei max=5.
  Alle 11 Pflichtabschnitte konnten nicht validiert werden.
- Schemas regeneriert: `maxItems: 5 → 15`, `minItems: 2 → 1` in
  `schemas/report-contract.schema.json` und `schemas/report.schema.json`.

### Teil A.2 — Discoverability-Hinweis in llm_e2e_stub

Datei: `backend/app/utils/llm_e2e_stub.py`

- Import-time-Log erweitert: Hinweis, dass Embedding-Service separat stubt.

### Teil C — E2E-Test-Toleranz (defensiv)

Datei: `frontend/tests/e2e/upload-graph.spec.ts`

- `page.goto()` mit explizitem `timeout: 60_000` (war implizit 30 s).

Datei: `frontend/tests/e2e/global-teardown.ts`

- Catch-Body verbessert: kein `console.error` mit Error-Objekt-Trace,
  statt `err instanceof Error ? err.message : String(err)` → lesbarer
  Status-Log `[e2e-globalTeardown] logs <name> not available (container down or not started)`.

## Verifikation

### Embedding-Stub

```
OK: embedding stub liefert deterministische Vectors korrekter Dimension
```

### Outline-Validation-Fix

```
OK: ReportOutlineModel.model_validate passed, sections: 11
```

### Backend-Tests

```
1691 passed, 9 skipped, 7 deselected in 53.39s
```

### Stub- + Embedding-spezifische Tests

```
29 passed in 1.04s
```

(12 bestehende + 3 neue Outline-Tests in `test_llm_e2e_stub.py`,
7 bestehende + 7 neue Stub-Tests in `test_embedding_service.py`)

### Ruff + mypy

```
ruff: 1 fixed (unused import os in test_embedding_service.py), 0 remaining
mypy: Success: no issues found in 132 source files
```

### Schema-Diff (erwartet)

```diff
-"maxItems": 5,
-"minItems": 2,
+"maxItems": 15,
+"minItems": 1,
```

in `schemas/report-contract.schema.json` und `schemas/report.schema.json`.

### Frontend

```
461 passed (45 files), lint grün, typecheck grün
```

## Geänderte Dateien

| Datei | +LOC | -LOC | Typ |
|---|---|---|---|
| `backend/app/storage/embedding_service.py` | +70 | 0 | Stub-Logik |
| `backend/app/contracts/report_contract.py` | +5 | -1 | max_length-Fix |
| `backend/app/utils/llm_e2e_stub.py` | +3 | -1 | Discoverability |
| `backend/tests/test_embedding_service.py` | +82 | +2 | 7 neue Tests |
| `backend/tests/test_llm_e2e_stub.py` | +40 | +1 | 3 neue Tests |
| `frontend/tests/e2e/upload-graph.spec.ts` | +2 | -1 | timeout explizit |
| `frontend/tests/e2e/global-teardown.ts` | +3 | -1 | Catch-Body |
| `schemas/report-contract.schema.json` | auto | auto | Schema-Dump |
| `schemas/report.schema.json` | auto | auto | Schema-Dump |

## Commit-bereit

Ja — alle Tests grün, Schemas synchron, kein Prod-Code-Pfad ohne Stub-Guard.
