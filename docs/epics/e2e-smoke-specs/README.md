# Epic · E2E-Smoke-Specs reparieren

Status: **Draft** — 2026-07-14
Owner: —
Verwandt: `.github/workflows/e2e-smokes.yml`, `frontend/tests/e2e/`

> **Statusquelle:** Dieses Epic ist ein **Diagnose-Dokument mit Stand
> 2026-07-14** und keine Live-Statusquelle. Der aktuelle, verifizierte
> Smoke-Status wird in [`docs/STATUS.md`](../../STATUS.md) und
> [Issue #739](https://github.com/arn0ld87/agora/issues/739) geführt (per
> `AGENTS.md`-Dokumentationshierarchie). Die Root-Cause-Analysen unten bleiben
> gültige Referenz; die Status-Spalten spiegeln den Draft-Stand, nicht den
> Merge-Fortschritt.

## Ziel

Sechs E2E-Smoke-Specs sind in `.github/workflows/e2e-smokes.yml` verdrahtet. Davon
ist nur `health.spec.ts` grün, fünf sind **pre-existing kaputt** (broken before
und unabhängig von diesem Epic). Dieses Epic macht alle fünf Smoke-Specs wieder
grün, ohne die Spec-Semantik zu verwässern — die Specs bleiben die Spec
(`AGENTS.md`: „Tests sind die Spec“).

Nicht-Ziel: Re-Add des `pull_request`-Triggers für die Smoke-Workflows. Der
Trigger wurde bewusst entfernt (siehe Commit `4a4fb0d0` „Revert ci(e2e): run
smokes on pull_request to main" / PR #731) und darf erst re-aktiviert werden,
wenn **alle fünf** Specs stabil grün laufen (siehe Trigger-Readd-Plan unten).

## Kontext: Workflow-Trigger

`.github/workflows/e2e-smokes.yml` läuft aktuell auf:

- `push: branches: [main]`
- `workflow_dispatch:`
- `schedule: cron '0 3 * * *'`

**Kein** `pull_request`-Trigger. Die Smoke-Jobs (health, upload-graph,
minimal-report, report-modes, golden-gate-accessibility, ai-model-picker) sind
als parallele Jobs definiert, jeder mit eigenem Playwright-Run
(`npx playwright test <spec>.spec.ts --reporter=list,github`).

## Spec-Übersicht

_Status-Spalte = Diagnose-Stand 2026-07-14 (historisch). Live-Status:
[`docs/STATUS.md`](../../STATUS.md) + [Issue #739](https://github.com/arn0ld87/agora/issues/739)._

| # | Spec | Pfad | Status |
|---|------|------|--------|
| 1 | Health-Smoke | `frontend/tests/e2e/health.spec.ts` | grün |
| 2 | Upload+Graph-Smoke | `frontend/tests/e2e/upload-graph.spec.ts` | rot |
| 3 | Minimalreport-Smoke | `frontend/tests/e2e/minimal-report.spec.ts` | rot |
| 4 | Report-Modes-Smoke | `frontend/tests/e2e/report-modes.spec.ts` | rot |
| 5 | Golden-Gate-A11y-Smoke | `frontend/tests/e2e/golden-gate-accessibility.spec.ts` | rot |
| 6 | AiModelPicker-Smoke | `frontend/tests/e2e/ai-model-picker.spec.ts` | rot |

---

## 2 · Upload+Graph-Smoke

**Spec-Pfad:** `frontend/tests/e2e/upload-graph.spec.ts`
**Job:** `upload-graph-smoke` (`e2e-smokes.yml:104`)

**Ablauf (laut Spec):** Markdown-Upload → Ontology → Graph-Build →
`pollGraphReady` → `GET /api/graph/data/<graph_id>` (API-Assertion, Schritt 6)
→ UI `page.goto('/process/<projectId>')` → `.graph-view` sichtbar
(Schritt 7, `upload-graph.spec.ts:165`).

**Fehler-Symptom:** `page.locator('.graph-view')` wird nicht sichtbar
(`upload-graph.spec.ts:165-168`, Timeout 30 s). Die vorgelagerte
API-Assertion `GET /api/graph/data` (Schritt 6, `:131-144`) bestätigt aber,
dass der Graph gebaut wurde und `nodes`-Array existiert (im Stub-Modus leer
aber valide). Der Backend-Flow ist also erfolgreich; der Break liegt in der
**UI/State-Verdrahtung**, nicht im Backend.

**Root-Cause:** `GraphCanvas.vue:4` rendert `<div v-if="graphData"
class="graph-view">`. `graphData` wird im UI-Pfad erst befüllt, wenn
`MainView`/GraphPanel `project.graph_id` aus dem Store liest und
`loadGraph(graph_id)` aufruft. Im aktuellen `design-v4`-AppShell-Port ist die
Verkettung `route /process/<projectId>` → Store `project.graph_id` →
`loadGraph` → `GraphCanvas.graphData` für den frisch hochgeladenen Stub-Graph
unterbrochen, sodass `v-if="graphData"` (`GraphCanvas.vue:4`) nie truthy wird
und `.graph-view`/`svg.graph-svg` (`:5`) nicht rendern. Die API liefert Daten,
die UI bekommt sie nicht in den Render-Zweig.

**Fix-Ansatz:**

1. Trace im `design-v4`-Port den Pfad `/process/:projectId` →
   `MainView`/`GraphPanel` → `useProjectStore`/`fetchGraphData` →
   `loadGraph(graph_id)` → `GraphCanvas`-Prop `graphData`.
2. Sicherstellen, dass nach `GET /api/graph/data` (oder projekt-gebundenem
   Polling) der `graphData`-Ref auf dem `GraphCanvas`-Wrapper gesetzt wird und
   `project.graph_id` nach Graph-Build in den Store propagated wird.
3. Keine Selektor-Änderung — `.graph-view`/`svg.graph-svg` bleiben der Anker.

---

## 3 · Minimalreport-Smoke

**Spec-Pfad:** `frontend/tests/e2e/minimal-report.spec.ts`
**Job:** `minimal-report-smoke` (`e2e-smokes.yml:187`)

**Ablauf:** Graph-Setup → 50 Stub-Personas seeden → `triggerReport` →
`pollReportReady` bis `completed` (Schritt 9, `:272`, Timeout 300 s) → UI
`page.goto('/report/<report_id>')` → `ol.outline` sichtbar
(`:291-295`) → 11 `span.outline-title` aus Snapshot
(`:304-310`) → `div.report-body.markdown-body` sichtbar (`:349-353`).

**Fehler-Symptom:** `ol.outline` wird nicht sichtbar
(`minimal-report.spec.ts:291-295`). Der Backend-Poll `pollReportReady`
(Schritt 9) ist zuvor erfolgreich — der Report erreicht den `completed`-Status
auf API-Ebene. Der Break liegt in der **UI-Render-Phase**, nicht im Backend.

**Root-Cause:** `ReportOutlinePanel.vue:55` rendert `<ol class="outline">`
unkonditional innerhalb des Panels; das Panel wird von `Step4Report.vue:436`
per `v-if="reportOutline"` gemountet. `reportOutline` wird in
`Step4Report.vue:255` nur gesetzt, wenn der Status-Poll ein `st.outline`
liefert **und** `ReportOutlineSchema.parse()` erfolgreich ist
(`try/catch` schluckt Parse-Fehler still → `reportOutline.value` bleibt
`null`). Im Stub-Modus erreicht der Report zwar `status="completed"`, aber
entweder liefert der Status-Endpoint kein `outline`-Feld oder die
`ReportOutlineSchema`-Parse schlägt fehl, sodass `v-if="reportOutline"`
(`Step4Report.vue:436`) falsch bleibt und `ol.outline` nie rendert. Da
`pollReportReady` nur auf `completed` prüft, nicht auf `outline`, wird der
Fehler erst in der UI-Assertion sichtbar.

**Fix-Ansatz:**

1. Im Status-Poll (`Step4Report.vue:255`) `recordSchemaError('outline', err)`
   nicht still schlucken — CI-Trace prüfen, ob `st.outline` vorhanden und
   schema-konform ist.
2. Entweder Backend liefert im Stub-Modus ein valides `outline`-Payload für
   `completed`-Reports, **oder** der `ReportOutlineSchema`-Spiegel driftet
   gegen das Backend-Contract (Layer-0-Spiegel-Check `dump_schemas`).
3. Schema-Drift prüfen: `cd backend && uv run python -m app.contracts.dump_schemas --check`
   und Zod-Spiegel in `frontend/src/contracts/` gegen Pydantic abgleichen.
4. Keine Selektor-Änderung — `ol.outline`/`span.outline-title` bleiben Anker.

---

## 4 · Report-Modes-Smoke

**Spec-Pfad:** `frontend/tests/e2e/report-modes.spec.ts`
**Job:** `report-modes-smoke` (`e2e-smokes.yml:273`)

**Ablauf:** `beforeAll` Shared-Setup (Upload+Graph+Simulation) → pro Modus
(`strict`/`balanced`/`explorative`) `triggerReport({ mode, forceRegenerate:
true })` → `pollReportReady` (`:154`) → Markdown-Export prüfen auf
`**Report-Modus:**` + Modus-Name (`:166-172`). Plus ein Default-Test ohne
`mode`-Param → erwartet `balanced` (`:182-205`).

**Fehler-Symptom:** `pollReportReady` (`report-modes.spec.ts:154`) kommt nicht
zurück — der Report erreicht nicht den `completed`-Zustand. Anders als beim
Minimalreport-Smoke bricht hier schon der Backend-Poll, nicht erst die
UI-Assertion.

**Root-Cause:** Der Report-Pipeline fehlt für `force_regenerate=true`-Trigger
mit `?mode=`-Param die Fortschreibung bis `completed`. Entweder terminiert
die Report-Generierung im Stub-Modus mit einem nicht-`completed`-Zustand
(`failed`/`error`/hängend), oder `force_regenerate`+`mode` schlagen fehl, weil
die Simulation aus dem Shared-Setup (`beforeAll`) für die
`force_regenerate`-Pfade keinen validen Report-Stumpf liefert. Da drei
sequenzielle `force_regenerate`-Läufe auf dieselbe `simulation_id` gehen
(`test.describe.serial`, `:139`) und der Report-Manager überlappende
Status-Files schreibt, ist ein weiterer möglicher Sub-Cause ein
Status-File-Race zwischen den Modi.

**Fix-Ansatz:**

1. Container-Logs aus dem `report-modes-smoke`-Job ziehen — finalen
   Report-Status (`failed`/`error`/`processing`) identifizieren.
2. `pollReportReady`-Helper um Debug-Output des letzten Status-Bodys
   erweitern (temporär), um zwischen „terminiert nicht-`completed`“ und
   „hängt in `processing`“ zu unterscheiden.
3. Backend: `api/report.py::_resolve_report_mode` (`:83`) +
   `force_regenerate`-Pfad prüfen — ob `?mode=` korrekt an
   `report_agent` durchgereicht wird und der Stub pro Modus deterministisch
   `completed` schreibt.
4. Serial-Race: sicherstellen, dass `force_regenerate=true` den vorigen
   Status-File atomar ersetzt, nicht überlappt schreibt.

---

## 5 · Golden-Gate-A11y-Smoke

**Spec-Pfad:** `frontend/tests/e2e/golden-gate-accessibility.spec.ts`
**Job:** `golden-gate-accessibility-smoke` (`e2e-smokes.yml:351`)

**Ablauf:** Pro Route (`/dashboard`, `/runs`, `/settings/general`,
`/settings/integrations`, `/settings/profile`, `/settings/api-keys`,
`/settings/llm-providers`, `/settings/embedding`, `/onboarding`,
Picker in `/settings/llm-routing`) wird `checkAccessibilityGate` gerufen:
axe-core ohne serious/critical violations, 320×800 ohne horizontalen Scroll,
Tab-Navigation, `:focus-visible`, `prefers-reduced-motion`.
(`golden-gate-accessibility.spec.ts:33-103`)

**Fehler-Symptom:** `assertNoCriticalViolations(axeResults)` schlägt fehl —
axe-core findet serious/critical violations auf mindestens einer der zehn
getesteten Routen. Der Test bricht beim ersten fehlgeschlagenen Gate ab;
welche Route genau trägt der Spec nicht bei (alle Routes sind separate
`test()`-Cases, Playwright reportiert pro Case).

**Root-Cause:** Eine oder mehrere der zehn Routen hat
serious/critical-axe-violations (z. B. fehlende `aria-label`/`role` an
interaktiven Elementen, Kontrast < 4.5:1, fokussierbare Elemente ohne
sichtbare Focus-Indikatoren, Heading-Hierarchy-Sprünge). Der
`design-v4`-AppShell-Port hat die Settings-Sub-Routes neu assembliert; die
A11y-Gates waren auf dem v3-Shell grün und drifteten beim Port.

**Fix-Ansatz:**

1. Job-Logs pro Case auswerten — welche Route(n) exact failen.
2. Pro fehlgeschlagener Route axe-core-Report im Trace
   (`playwright-trace-golden-gate-accessibility`) inspizieren.
3. Violations an der Quelle beheben (Komponenten-Ebene), nicht die Gate-Schwelle
   senken — `assertNoCriticalViolations` bleibt strict.
4. `check320pxNoHorizontalScroll` / `checkFocusVisible` separat validieren,
   falls die Verletzung in den Sub-Gates (nicht axe-core) liegt.

---

## 6 · AiModelPicker-Smoke

**Spec-Pfad:** `frontend/tests/e2e/ai-model-picker.spec.ts`
**Job:** `ai-model-picker-smoke` (`e2e-smokes.yml:429`)

**Ablauf:** `login` → `/settings/llm-routing` → Run-ID (`run_e2e_model_picker`)
ins `llm-routing-run-id`-Feld eintragen
(`ai-model-picker.spec.ts:55`, via `LlmRoutingTestId.runId`) → warten bis
Stage-Picker für `document_ingest` sichtbar (`:57`,
`getStagePicker(page, STAGE)`) → 5 Sub-Tests (Tastatur-Navigation, Suche,
Online-Modell verfügbar, Offline-Connection leer, Stage-Override landet im
`ai_route`).

**Fehler-Symptom:** `getStagePicker(page, 'document_ingest')` wird nicht
sichtbar (`ai-model-picker.spec.ts:57`, `beforeEach`), die Sub-Tests laufen
gar nicht erst. Helper `getStagePicker` (`helpers/aiModelPicker.ts:96-98`)
resolviert `[data-testid="llm-routing-stage-row"][data-stage="document_ingest"]
.ai-model-picker`.

**Root-Cause (ursprüngliche Annahme revidiert):** Die ursprüngliche Hypothese,
`getByTestId('llm-routing-run-id')` sei durch die Slice-7.6-AiModelPicker-
Migration entfernt/umbenannt worden, trifft auf den aktuellen `main` **nicht
zu** — das testId-Register ist intakt:
`frontend/src/contracts/testIds.ts:36` definiert `runId: 'llm-routing-run-id'`,
und `frontend/src/views/Settings/LlmRoutingView.vue:101` bindet es
`:data-testid="LlmRoutingTestId.runId"` an das Run-ID-Input. Auch die Route
`/settings/llm-routing` existiert (`router/index.ts:93-95`) und
`get_run_llm_routing` (`backend/app/api/llm_routing.py:108`) synthetisiert für
unbekannte `run_id` einen Default-Config (`RuntimeRunConfig.load_config()`),
sodass das `v-if="selectedRunIdTrimmed"` (`Settings/LlmRoutingView.vue:119`)
das `RunLlmRoutingPanel` mountet. Der Break liegt eine Ebene tiefer:
`RunLlmRoutingPanel` (`components/LlmRouting/LlmRoutingView.vue:160`) rendert
die Stage-Rows erst unter `v-if="routing"`. Wenn der `getRunLlmRouting`-Call
für die synthetische `run_e2e_model_picker` im E2E-Stack kein `routing`-Objekt
liefert (z. B. Discovery schlägt fehl, `mock-models`-Service nicht erreicht,
oder `routing`-Ref wird nicht gesetzt), bleiben Stage-Row + AiModelPicker
weg → `getStagePicker` timed out.

**Fix-Ansatz:**

1. Job-Trace `playwright-trace-ai-model-picker` prüfen: ist das
   `llm-routing-run-id`-Input sichtbar (bestätigt, dass testId+Route leben)?
   Wenn ja, ist der Break bei `v-if="routing"` (Stage-Row fehlt), nicht beim
   Run-ID-Input.
2. Sicherstellen, dass der `mock-models`-nginx-Service (Compose-Override aus
   `scripts/e2e-up.sh`) im `ai-model-picker-smoke`-Job läuft und
   `getRunLlmRouting` ein nicht-null `routing` zurückgibt.
3. Falls `routing` null bleibt: `RunLlmRoutingPanel.onMounted` →
   `load()`-Pfad (`getRunLlmRouting` + `loadProviders`) gegen den E2E-Stack
   validieren; ggf. ein Stub-Routing für unbekannte Run-IDs im Backend
   garantieren (Spec-Kommentar `:18-23` verspricht das bereits).
4. Keine testId-Änderung — `LlmRoutingTestId.runId`/`stageRow`/`stageSave`
   bleiben Anker.

---

## Trigger-Readd-Plan

**Status-Quo:** `.github/workflows/e2e-smokes.yml` triggert auf
`push: [main]` + `schedule` + `workflow_dispatch` — **kein** `pull_request`.
Der `pull_request`-Trigger wurde in PR #731 entfernt (Revert
`4a4fb0d0`), weil die Smokes auf Feature-PRs roteten und den PR-Workflow
blockierten.

**Readd-Bedinging:** Sobald **alle fünf** Smoke-Specs (Upload+Graph,
Minimalreport, Report-Modes, Golden-Gate-A11y, AiModelPicker) auf `main`
stabil grün laufen — idealerweise über drei aufeinanderfolgende
Schedule-Läufe ohne Rot — wird der `pull_request`-Trigger für die
Smoke-Workflows in einem **Folge-PR** re-add-ed.

**Readd-Shape (Folge-PR):**

```yaml
on:
  push:
    branches: [main]
  pull_request:        # re-add
  workflow_dispatch:
  schedule:
    - cron: '0 3 * * *'
```

Der Folge-PR **nicht** mit den Spec-Fixes mischen — erst grüne Specs
nachweisen, dann den Trigger in einem separaten PR re-add-en, damit ein
Trigger-Rollback isoliert möglich bleibt (analog PR #731).

## Definition of Done

- [ ] Alle 6 E2E-Smoke-Specs grün auf `main` (health bleibt grün).
- [ ] Drei aufeinanderfolgende Schedule-Läufe (`0 3 * * *`) ohne Rot.
- [ ] `pull_request`-Trigger in Folge-PR re-add-ed.
- [ ] Keine Spec-Semantik geschwächt (Selektoren/Gate-Schwellen unverändert).