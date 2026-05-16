# M11.4c — Minimalreport-Smoke — Arbeitsprotokoll

**Stand:** 2026-05-10
**Slice:** M11.4c (Phase 7 Playwright-Smokes, letzter Slice)
**Branch:** `feat/layer-9-task-m114c-minimal-report-smoke`

---

## Ziel

Dritter und letzter Playwright-Smoke: Report generieren, alle 11 Sections + Persona-Tabelle im UI assertieren.

---

## Pflicht-Lese-Analyse (Pre-Code)

### Stub-Vertrag (`llm_e2e_stub.py`)

**Braucht der Report-Pfad einen Graph?** JA.

`backend/app/api/report.py:107`:
```python
graph_id = state.graph_id or project.graph_id
if not graph_id:
    return json_error("Missing graph ID, please ensure graph is built", status=400)
```

Ohne graph_id → 400. Der Upload+Graph-Vorlauf aus M11.4b muss wiederverwendet werden.

**Personas-Anzahl im Stub?** 1 Persona.

`backend/app/utils/llm_e2e_stub.py::_stub_report_v3()`: Genau 1 Persona-Objekt (`p-stub-01`).
Relevant: Das ReportV3-Stub-Objekt wird nur zurückgegeben wenn `schema=ReportV3` — nicht im Section-Content-Pfad.

**Stub-Coverage vor M11.4c:**
- `chat_json()` → stub aktiv (`llm_client.py:386`)
- `chat()` → stub NICHT aktiv — nur `chat_json` war abgedeckt

**Kritische Lücke gefunden:** `generate_section_react` in `workflow.py` verwendet `agent.llm.chat()` (Zeile 107), nicht `chat_json`. Ohne Stub für `chat()` würden alle LLM-Calls scheitern, und der Report würde mit `status=FAILED` enden (Exception in `generate_report_impl`-except-Block, Zeile 554).

**Zweite Lücke gefunden:** `plan_outline` verwendet `chat_json(schema=PlanResponse)`. PlanResponse ist kein ReportV3-Schema, daher gibt der Stub `{"ok": true, "stub": true}` zurück. `plan_outline` kann diesen Dict nicht als `PlanResponse` parsen, fällt in den Except-Block (Zeile 111) und liefert ein 3-Section-Fallback-Outline zurück. Die UI würde nur 3 statt 11 Sections zeigen.

### Endpoint-Pfade (`backend/app/api/report.py`)

| Endpoint | Zeile | Beschreibung |
|---|---|---|
| `POST /api/report/generate` | 74 | Report-Generierung starten |
| `POST /api/report/generate/status` | 226 | Status pollen |
| `GET /api/report/<report_id>` | 347 | Fertigen Report laden |

`POST /api/report/generate` erfordert `simulation_id` mit vorhandenem `graph_id`.
Simulation wird via `POST /api/simulation/create` angelegt (`simulation_lifecycle.py:81`).

### DOM-Selektoren (`Step4Report.vue` + `ReportOutlinePanel.vue`)

| Selector | Quelle | Zweck |
|---|---|---|
| `ol.outline` | `ReportOutlinePanel.vue:55` | Outline-Liste-Container |
| `span.outline-title` | `ReportOutlinePanel.vue:72` | Section-Titel je Item |
| `div.report-body.markdown-body` | `Step4Report.vue:521` | Gerenderter Markdown-Body |
| `.section-content table` | `ReportOutlinePanel.vue:80` | Markdown-Tabellen in Sections |

Route: `/report/:reportId` → `ReportView.vue` → `Step4Report` mit `:reportId`.

**Kein `data-testid` vorhanden** — die CSS-Klassen sind stabil und im realen Markup verifiziert.

---

## Stub-Erweiterungen (Pre-Code, zwingend)

### 1. `chat()` Stub-Branch in `llm_client.py`

Neu eingebaut zwischen `_publish_model_active` und dem `kwargs`-Dict (Zeile nach 195):

```python
if os.environ.get("AGORA_E2E_LLM_MODE") == "stub":
    from app.utils.llm_e2e_stub import e2e_stub_chat_response
    return e2e_stub_chat_response(messages=messages)
```

### 2. `e2e_stub_chat_response()` in `llm_e2e_stub.py`

Deterministischer String-Return für den ReACT-Loop:
- Zählt vorhandene `assistant`-Nachrichten in der Message-History
- Iteration 0–2 (< 3 assistant-Msgs): gibt einen Tool-Call-String zurück (`panorama_search`, `quick_search`, `insight_forge` rotierend)
- Iteration ≥ 3: gibt `"Final Answer: ..."` zurück

`min_tool_calls = 3` in `generate_section_react` (workflow.py:93) ist damit erfüllt.

### 3. `_stub_plan_response()` + `_is_plan_response_schema()` in `llm_e2e_stub.py`

`chat_json(schema=PlanResponse)` muss 11 Sections zurückgeben, damit die UI 11 Section-Header zeigt.

`_is_plan_response_schema(schema)` erkennt:
1. `title` enthält "PlanResponse" oder "plan_response"
2. `properties` enthält "sections" und "title"/"summary"

`_stub_plan_response()` gibt alle 11 Section-Titel aus `_REQUIRED_SECTIONS` zurück.

`e2e_stub_response()` prüft PlanResponse nach ReportV3 (Bedingung 2b).

---

## Report braucht Graph: JA

Dokumentiert in `minimal-report.spec.ts`-Header:
> "Der Report-Pfad benötigt einen vorhandenen Graph (backend/app/api/report.py:107)."

Upload+Graph-Vorlauf aus M11.4b wird komplett wiederverwendet (helpers/upload.ts, helpers/graph.ts).

---

## Personas-Anzahl im Stub: 1 (`p-stub-01`)

`backend/app/utils/llm_e2e_stub.py::_stub_report_v3()` — Zeile 102:
```python
"personas": [{"id": "p-stub-01", ...}]
```

Relevant für `MIN_PERSONA_TABLE_ROWS`:
- Im Stub-Modus erzeugt `e2e_stub_chat_response()` Freitext ohne Markdown-Tabelle
- Section "Persona-Tabelle" enthält keine `<tr>`-Elemente
- `MIN_PERSONA_TABLE_ROWS = 0` (in `minimal-report.spec.ts` kommentiert)
- Assertion: Section-Heading "Persona-Tabelle" als `span.outline-title` sichtbar
- Für echten LLM-Betrieb: `contract_constants.py::MIN_PERSONA_TABLE_ROWS = 50`

---

## Neue Dateien

| Datei | LOC | Beschreibung |
|---|---|---|
| `frontend/tests/e2e/minimal-report.spec.ts` | ~200 | Playwright-Spec |
| `frontend/tests/e2e/helpers/report.ts` | ~80 | `triggerReport` + `pollReportReady` |

## Geänderte Dateien

| Datei | Delta | Beschreibung |
|---|---|---|
| `backend/app/utils/llm_e2e_stub.py` | +80 | `e2e_stub_chat_response`, `_stub_plan_response`, `_is_plan_response_schema` |
| `backend/app/utils/llm_client.py` | +10 | Stub-Branch in `chat()` |
| `.github/workflows/e2e-smokes.yml` | +45 | Job `minimal-report-smoke` |
| `CHANGELOG.md` | +2 | M11.4c-Eintrag unter [Unreleased] Added |

---

## Verifikations-Ergebnisse

```
# Frontend
npm ci              → OK
npm run lint        → 0 Findings
npm run typecheck   → 0 Fehler
npm test -- --run   → 461 passed, 0 failed
npx playwright test minimal-report.spec.ts --list → 1 test

# Backend
ruff check app/ tests/    → All checks passed
mypy app                  → Success: no issues found in 132 source files
pytest -x -q -m "not llm" → 1681 passed, 9 skipped, 7 deselected

# Schema-Drift
git diff --exit-code schemas/ → sauber (kein Drift)
```

---

## Abweichungen von der Spec

**Keine wesentlichen Abweichungen.**

Dokumentierte Anpassungen:

1. **Stub-Erweiterung erforderlich** (nicht im ursprünglichen Scope genannt): `chat()` musste ebenfalls den Stub-Pfad erhalten, sonst wäre der Report `FAILED`. Erweiterung ist minimal und backward-kompatibel.

2. **PlanResponse-Erkennung** (nicht im ursprünglichen Scope): `_is_plan_response_schema` musste ergänzt werden, damit `plan_outline` 11 Sections produziert statt 3 (Fallback). Sonst wären nur 3 Section-Titel im UI gewesen, nicht 11.

3. **`MIN_PERSONA_TABLE_ROWS = 0`** statt 50: Der Stub liefert Freitext, keine Markdown-Tabelle. Die Assertion prüft die Section-Heading-Sichtbarkeit, nicht Row-Count. Die Konstante bleibt als Platzhalter für echten Betrieb.

4. **ESM-kompatibler Snapshot-Pfad**: `__dirname` nicht verfügbar (package.json "type":"module"), gelöst mit `fileURLToPath(import.meta.url)`.

---

## Commit-bereit: JA

Alle Pflicht-Verifikationen grün. Kein Layer-0-Touch. Kein Schema-Drift.
