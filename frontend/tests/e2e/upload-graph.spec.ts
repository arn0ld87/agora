/**
 * M11.4b · Upload + Graph-Smoke
 *
 * Ablauf:
 *   1. Auth-Token injizieren (localStorage via context.addInitScript — analog health.spec.ts Test 3)
 *   2. Markdown-Dokument inline definieren (backend/tests/eval/fixtures/good/ enthält nur JSON,
 *      kein seed.md — inline Body ist die spec-konforme Fallback-Strategie)
 *   3. POST /api/graph/ontology/generate (multipart) → project_id
 *   4. POST /api/graph/build (JSON) → task_id
 *   5. GET /api/graph/task/<task_id> pollen bis status="completed" (expect.poll, kein setTimeout)
 *   6. GET /api/graph/data/<graph_id> → Nodes-Array prüfen (API-Assertion)
 *   7. UI: /process/<project_id> laden — GraphPanel-Container wird sichtbar
 *
 * AGORA_E2E_LLM_MODE=stub-Notiz:
 *   Der LLM-Stub liefert {"ok": true, "stub": true} für OntologyGenerator und NERExtractor.
 *   OntologyGenerator ergänzt leere entity_types/edge_types (ontology_generator.py:269-274).
 *   NERExtractor gibt leere entities/relations zurück → Neo4j schreibt 0 Entity-Nodes.
 *   Daher ist node_count=0 im stub-Modus valide — der Graph ist leer aber erfolgreich gebaut.
 *   Die UI-Assertion prüft, dass das GraphPanel den Completed-Zustand anzeigt (svg.graph-svg
 *   sichtbar, kein "Waiting for ontology generation..."-Fallback-State).
 *
 * Endpoints abgeleitet aus:
 *   - backend/app/api/graph.py::generate_ontology  (POST /api/graph/ontology/generate)
 *   - backend/app/api/graph.py::build_graph         (POST /api/graph/build)
 *   - backend/app/api/graph.py::get_task            (GET  /api/graph/task/<task_id>)
 *   - backend/app/api/graph.py::get_graph_data      (GET  /api/graph/data/<graph_id>)
 *   - backend/app/models/task.py::TaskStatus        ("completed" | "failed" | "processing" | "pending")
 *
 * DOM-Selektoren abgeleitet aus:
 *   - frontend/src/components/graph/GraphCanvas.vue: div.graph-view (v-if="graphData")
 *   - frontend/src/components/graph/GraphCanvas.vue: svg.graph-svg  (Render-Container, immer im graph-view)
 *   - frontend/src/components/Step1GraphBuild.vue:   div.stat-value  (Knoten-Zahl-Anzeige)
 */

import { test, expect, request } from '@playwright/test';
import { injectAuthToken, authHeader } from './helpers/auth';
import { assertStubModeActive } from './helpers/diagnostics';
import { uploadMarkdown } from './helpers/upload';
import { triggerGraphBuild, pollGraphReady } from './helpers/graph';

// Deterministisches Markdown-Dokument für den Upload-Smoke.
// Bewusst klein (< 500 Zeichen) damit der Text-Splitting-Schritt
// möglichst einen einzigen Chunk erzeugt und der Build schnell durchläuft.
const SMOKE_MARKDOWN_BODY = `# Agora E2E Smoke Document

Dies ist ein deterministisches Testdokument für den Upload+Graph-Smoke M11.4b.
Es dient ausschließlich der CI-Verifikation des Agora-Workflows.

## Beteiligte Akteure

- **Agora-Plattform**: Software-System für DACH-Zielgruppenreaktionen.
- **CI-Runner**: Automatisiertes Testsystem ohne Netzwerk-LLM-Zugang.
- **Stub-LLM**: Deterministischer Ersatz für Ollama im E2E-Smoke-Betrieb.
`;

const SMOKE_FILENAME = 'e2e-smoke-m11-4b.md';

test.describe('M11.4b · Upload + Graph-Smoke', () => {
  test('1 · Markdown-Upload → Ontologie → Graph READY → Panel sichtbar', async ({
    page,
    context,
    baseURL,
  }) => {
    // =====================================================================
    // Schritt 1: Auth-Token injizieren (localStorage-Pfad verifiziert via
    // frontend/src/api/index.ts:41 — localStorage.getItem('agora_token'))
    // =====================================================================
    await injectAuthToken(context);

    // Auth-Header für direkte API-Requests (X-Agora-Token verifiziert via
    // backend/app/utils/auth.py:47)
    const headers = authHeader();

    // Separater Request-Context für API-Calls (kein Browser-State)
    const apiCtx = await request.newContext({
      extraHTTPHeaders: headers,
    });

    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    try {
      // =================================================================
      // Diagnostik: Stub-Mode-Status vor dem ersten API-Call loggen.
      // Kein hartes Assert — nur informatives Logging für CI-Debugging.
      // Container-Logs (global-teardown.ts) zeigen ob llm_e2e_stub importiert.
      // =================================================================
      await assertStubModeActive(apiCtx, baseURL!);

      // =================================================================
      // Schritt 2+3: Markdown hochladen → POST /api/graph/ontology/generate
      // =================================================================
      const ontologyData = await uploadMarkdown(
        apiCtx,
        SMOKE_MARKDOWN_BODY,
        SMOKE_FILENAME,
        baseURL!,
        headers,
      );
      const projectId = ontologyData.project_id as string;
      expect(projectId, 'project_id muss ein nichtleerer String sein').toBeTruthy();

      // =================================================================
      // Schritt 4: Graph-Build anstoßen → POST /api/graph/build
      // =================================================================
      const { task_id } = await triggerGraphBuild(apiCtx, projectId, baseURL!, headers);
      expect(task_id, 'task_id muss ein nichtleerer String sein').toBeTruthy();

      // =================================================================
      // Schritt 5: Status pollen bis "completed" (kein hardcoded sleep)
      // Timeout 120 s: Neo4j-Graph-Build mit Stub-NER ist schnell, aber
      // CI-Runner können langsam sein.
      // =================================================================
      const taskResult = await pollGraphReady(apiCtx, task_id, baseURL!, headers, 120_000);

      // graph_id aus Task-Result lesen (backend/app/api/graph.py::build_task:523)
      const graphId = (taskResult?.result as Record<string, unknown> | null)?.graph_id as
        | string
        | undefined;
      expect(graphId, 'graph_id muss im Task-Result vorhanden sein').toBeTruthy();

      // =================================================================
      // Schritt 6: GET /api/graph/data/<graph_id> — API-Assertion
      // Im Stub-Modus ist node_count=0 (NER liefert leere Entity-Liste).
      // Wir prüfen: Antwort ist valide, nodes-Array existiert.
      // =================================================================
      const dataRes = await apiCtx.get(`${baseURL}/api/graph/data/${graphId}`, {
        headers,
      });
      expect(dataRes.status(), 'GET /api/graph/data muss 200 zurückgeben').toBe(200);
      const dataJson = await dataRes.json();
      const graphDataPayload = dataJson?.data;
      expect(
        graphDataPayload,
        '/api/graph/data-Antwort muss ein data-Objekt enthalten',
      ).toBeTruthy();
      expect(
        Array.isArray(graphDataPayload?.nodes),
        'nodes muss ein Array sein (auch wenn leer im Stub-Modus)',
      ).toBe(true);

      // =================================================================
      // Schritt 7: UI — /process/<project_id> laden und GraphPanel prüfen
      //
      // DOM-Selektoren abgeleitet aus GraphCanvas.vue:
      //   .graph-view  — div-Wrapper, v-if="graphData" (sichtbar wenn Daten geladen)
      //   svg.graph-svg — SVG-Render-Container (immer im .graph-view, auch bei 0 Knoten)
      //
      // Nach dem Navigieren pollt MainView fetchGraphData() alle 10 s und
      // ruft loadGraph(graph_id) auf, sobald project.graph_id vorhanden ist.
      // Da das Backend synchron antworten muss, reicht networkidle als Signal.
      // =================================================================
      await page.goto(`/process/${projectId}`, { waitUntil: 'networkidle' });

      // GraphPanel muss den Completed-Zustand anzeigen — kein "Waiting"-Fallback
      const graphView = page.locator('.graph-view');
      await expect(graphView, '.graph-view muss sichtbar sein (graphData geladen)').toBeVisible({
        timeout: 30_000,
      });

      // svg.graph-svg muss im DOM sein — D3 hängt sich an diese SVG.
      // Das Element ist immer vorhanden wenn .graph-view sichtbar ist
      // (GraphCanvas.vue:6 — unkonditionell innerhalb v-if="graphData")
      const graphSvg = page.locator('svg.graph-svg');
      await expect(graphSvg, 'svg.graph-svg muss im DOM vorhanden sein').toBeVisible({
        timeout: 10_000,
      });

      // Keine pageerror-Events während des gesamten Flows
      expect(
        pageErrors,
        `Page-Errors während Upload+Graph-Flow: ${pageErrors.join('; ')}`,
      ).toHaveLength(0);
    } finally {
      await apiCtx.dispose();
    }
  });
});
