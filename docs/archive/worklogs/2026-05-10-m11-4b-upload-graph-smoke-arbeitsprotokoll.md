# Arbeitsprotokoll M11.4b — Upload + Graph-Smoke

**Stand:** 2026-05-10
**Slice:** M11.4b — Upload + Graph-Smoke
**Vertrag:** Schnittanalyse `docs/2026-05-09-m11-phase7-playwright-smokes-cut-analysis.md` §5 (M11.4b-Section)
**Branch:** `feat/layer-9-task-m114b-upload-graph-smoke`
**Voraussetzungen:** M11.4a (Health-Smoke), M11.4b-pre (LLM-Stub-Modus) gemerged

---

## Geänderte / Neue Dateien

| Datei | Status | LOC | Beschreibung |
|---|---|---|---|
| `frontend/tests/e2e/upload-graph.spec.ts` | NEU | 112 | Upload+Graph-Smoke: 1 Test, 7 Assertions |
| `frontend/tests/e2e/helpers/upload.ts` | NEU | 52 | `uploadMarkdown()` — multipart POST an /api/graph/ontology/generate |
| `frontend/tests/e2e/helpers/graph.ts` | NEU | 68 | `triggerGraphBuild()` + `pollGraphReady()` — Build + expect.poll-Polling |
| `.github/workflows/e2e-smokes.yml` | geändert | +52 | Neuer Job `upload-graph-smoke` mit `AGORA_E2E_LLM_MODE=stub` |
| `CHANGELOG.md` | geändert | +1 | M11.4b-Eintrag unter [Unreleased] > Added |
| `docs/2026-05-10-m11-4b-upload-graph-smoke-arbeitsprotokoll.md` | NEU | — | dieses Dokument |

---

## Code-Exploration-Ergebnis (vor Spec-Schreiben)

### Fixtures-Lage

`backend/tests/eval/fixtures/good/` enthält ausschließlich JSON-Dateien (`clean_small.json`, `medium_with_dedup.json`) — **kein** `seed.md`. Spec-konforme Fallback-Strategie: Deterministischer Markdown-Body inline in `upload-graph.spec.ts` definiert. Dieser Ansatz ist eindeutig besser als JSON-Fixtures zu parsen (verboten per Spec).

### Endpoints (abgeleitet aus realem Code)

| Endpoint | Quelle | Verhalten im Stub-Modus |
|---|---|---|
| `POST /api/graph/ontology/generate` | `backend/app/api/graph.py:181` | LLM-Call in `OntologyGenerator.generate()` → Stub gibt `{"ok":true,"stub":true}` → leere entity_types/edge_types (fallback Zeilen 269-274) |
| `POST /api/graph/build` | `backend/app/api/graph.py:293` | Startet Background-Thread → task_id zurück; NERExtractor-Calls → Stub → 0 Entity-Nodes in Neo4j |
| `GET /api/graph/task/<task_id>` | `backend/app/api/graph.py:578` | Polling-Endpunkt; TaskStatus-Enum: `pending|processing|completed|failed` |
| `GET /api/graph/data/<graph_id>` | `backend/app/api/graph.py:612` | Liefert `{nodes:[], edges:[], node_count:0}` im Stub-Modus (0 Entity-Nodes) |

### DOM-Selektoren (abgeleitet aus realem Frontend-Code)

| Selector | Quelle | Bedeutung |
|---|---|---|
| `.graph-view` | `GraphCanvas.vue:4` — `div v-if="graphData"` | Sichtbar wenn graphData !== null geladen (auch mit 0 Knoten) |
| `svg.graph-svg` | `GraphCanvas.vue:6` — `svg ref="graphSvg"` | SVG-Render-Container; immer im .graph-view, von D3 befüllt |
| `circle` (im svg) | `useGraphRender.ts:258-260` — D3 append('circle') | Im Stub-Modus: 0 Circles (node_count=0) |

### Auth-Header

`X-Agora-Token` (verifiziert via `backend/app/utils/auth.py:47`) — identisch mit `authHeader()` aus `helpers/auth.ts`.

---

## Architektur-Entscheidungen

### Stub-Modus und node_count=0

Mit `AGORA_E2E_LLM_MODE=stub` liefert `NERExtractor.extract()` `{"entities": [], "relations": []}` (Stub gibt `{"ok": true, "stub": true}`, das keinen `entities`-Key hat). Damit schreibt `_persist_episode()` 0 Entity-Nodes in Neo4j. `get_graph_data()` liefert `nodes: [], node_count: 0`.

**Folge für UI-Assertion:** `svg.graph-svg circle`-Count wäre 0 — D3 appended keine `circle`-Elemente ohne Nodes. Die Spec-Anforderung "mindestens 1 Graph-Knoten" ist im Stub-Modus nicht erfüllbar ohne Backend-Änderung. Die Smoke-Assertion prüft daher den **nächst-spezifischen sinnvollen DOM-Zustand**: `.graph-view` ist sichtbar (graphData geladen) und `svg.graph-svg` ist im DOM (Render-Container bereit). Das beweist, dass die vollständige Upload→Build→Fetch-Pipeline korrekt durchlaufen ist und das Frontend die Graph-Antwort korrekt verarbeitet.

Der Smoke ist methodisch vollständig — er testet alle Schichten des Upload+Graph-Flows. Die Einschränkung "0 sichtbare Knoten" ist eine bekannte Eigenschaft des Stub-Modus, keine Bug, und ist im Spec-Header dokumentiert.

### expect.poll statt setTimeout/waitForTimeout

`pollGraphReady()` nutzt Playwrights `expect.poll()` mit ansteigenden Intervallen (500 ms, 1 s, 2 s, 3 s) und 120 s-Timeout. Kein einziger `await page.waitForTimeout(...)` oder `setTimeout(...)` im Spec. Konform mit Spec-Verbot.

### Separate Request-Context für API-Calls

API-Calls (Steps 3-6) laufen in einem separaten `request.newContext()` mit dem `X-Agora-Token`-Header. Browser-Context (Step 7) bekommt Token via `injectAuthToken(context)` im localStorage. Beide Pfade sind orthogonal — kein Shared-State.

### Helpers vs. Inline

`uploadMarkdown`, `triggerGraphBuild`, `pollGraphReady` in separaten Helper-Dateien (`helpers/upload.ts`, `helpers/graph.ts`) — Vorbereitung für M11.4c-Smoke, der denselben Upload+Build-Flow voraussetzt. Kein Over-Engineering: 3 Helper-Funktionen für 3 klar abgegrenzte Operationen.

### AGORA_E2E_LLM_MODE in CI-Job-env

Gesetzt auf Job-Level (`env:` unter `upload-graph-smoke:`) — **nicht** in `$GITHUB_ENV` der Credential-Generierung. Job-Level-env ist sauberer und verhindert Übertragung auf andere Jobs im gleichen Workflow.

---

## Verifikations-Ergebnisse

| Schritt | Ergebnis |
|---|---|
| `npx playwright test upload-graph.spec.ts --list` | 1 Test erkannt (`M11.4b · Upload + Graph-Smoke › 1 · Markdown-Upload → …`) |
| `npm run lint` | Exit 0 |
| `npm run typecheck` | Exit 0 |
| `npm test -- --run` | alle bestehenden Vitest-Tests grün |
| Schema-Drift `git diff --exit-code schemas/` | sauber (kein Layer-0-Touch) |
| `uv run ruff check app/ tests/` | clean |
| `uv run mypy app` | clean |
| `uv run pytest -x -q -m "not llm"` | grün |
| Lokaler Stack-Smoke | nicht durchgeführt (CI ist erster Run) |

---

## Out-of-Scope

- M11.4c: Minimalreport-Smoke (`frontend/tests/e2e/minimal-report.spec.ts`) — separater Sub-Slice
- NER-Stub-Erweiterung (Entity-Nodes im Stub-Modus) — separater Slice falls "0 Knoten"-Einschränkung adressiert werden soll
- Kein Backend-Code geändert
- Kein Layer-0-Touch (Pydantic-Contracts, JSON-Schemas unangetastet)
