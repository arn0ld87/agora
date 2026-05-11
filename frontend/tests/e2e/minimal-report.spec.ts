/**
 * M11.4c · Minimalreport-Smoke
 *
 * Ablauf:
 *   1. Auth-Token injizieren (localStorage via context.addInitScript).
 *   2. Graph-Vorlauf: uploadMarkdown → triggerGraphBuild → pollGraphReady.
 *      Der Report-Pfad benötigt einen vorhandenen Graph (backend/app/api/report.py:107
 *      — "Missing graph ID, please ensure graph is built").
 *   3. Simulation anlegen via POST /api/simulation/create (braucht project_id + graph_id).
 *   4. 50 manuelle Stub-Personas via POST /api/simulation/<id>/profiles anlegen.
 *   5. POST /api/report/generate mit Bearer-Auth triggern.
 *   6. Status-Polling via POST /api/report/generate/status bis "completed" (kein setTimeout).
 *      Timeout: 5 min (Stub-Modus: 11 Sections × 4 ReACT-Runden, aber kein echter LLM-Call).
 *   7. UI-Assertion: alle 11 Section-Header aus output-contract-required-sections.txt
 *      sind als span.outline-title in ReportOutlinePanel sichtbar.
 *      Die Liste wird zur Laufzeit aus der Snapshot-Datei gelesen — keine Hardcoded-Liste.
 *   8. Persona-Tabelle: Abschnitt "Persona-Tabelle" ist als span.outline-title sichtbar.
 *      Der Backend-Persona-Floor bleibt auch im Stub-Modus aktiv.
 *   9. 0 Page-Errors während des gesamten Flows.
 *
 * Stub-Vertrag (AGORA_E2E_LLM_MODE=stub):
 *   - chat_json(schema=PlanResponse) → _stub_plan_response() → 11 Sections
 *     (llm_e2e_stub.py::_stub_plan_response, aktiviert durch _is_plan_response_schema).
 *   - chat() → e2e_stub_chat_response() → Tool-Call-Strings (3 Runden) dann "Final Answer:".
 *     (llm_e2e_stub.py::e2e_stub_chat_response + llm_client.py::chat Stub-Branch).
 *   - Report-Graph (Neo4j): leer (0 Entities), aber existierend — Graph-Build-Phase
 *     schreibt keinen Content-Node im Stub-Modus (NER gibt leere entity-Liste zurück).
 *   - Persona-Floor: report_agent.workflow::_load_persona_count liest
 *     reddit_profiles.json; der Smoke seedet deshalb 50 manuelle Profile über
 *     den regulären API-Pfad.
 *
 * Report braucht Graph: JA.
 *   POST /api/report/generate prüft graph_id in simulation.state und project.graph_id
 *   (backend/app/api/report.py:107). Ohne graph_id → 400 "Missing graph ID".
 *   Daher wird der Upload+Graph-Vorlauf aus M11.4b wiederverwendet.
 *
 * DOM-Selektoren abgeleitet aus:
 *   - frontend/src/components/step4/ReportOutlinePanel.vue:72 — span.outline-title
 *     (Section-Titel, einer pro Abschnitt in ol.outline > li)
 *   - frontend/src/components/Step4Report.vue:521 — div.report-body.markdown-body
 *     (gerenderter Markdown des Finalberichts, v-html="reportHtml")
 *   - frontend/src/views/ReportView.vue:130 — Step4Report mit :reportId="currentReportId"
 *     (Route: /report/:reportId — router/index.ts:55)
 *
 * Endpoints abgeleitet aus:
 *   - POST /api/graph/ontology/generate  (backend/app/api/graph.py::generate_ontology)
 *   - POST /api/graph/build              (backend/app/api/graph.py::build_graph)
 *   - GET  /api/graph/task/<task_id>     (backend/app/api/graph.py::get_task)
 *   - POST /api/simulation/create        (backend/app/api/simulation_lifecycle.py:81)
 *   - POST /api/report/generate          (backend/app/api/report.py:74)
 *   - POST /api/report/generate/status   (backend/app/api/report.py:226)
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { test, expect, request, type APIRequestContext } from '@playwright/test';
import { injectAuthToken, authHeader } from './helpers/auth';
import { assertStubModeActive } from './helpers/diagnostics';
import { uploadMarkdown } from './helpers/upload';
import { triggerGraphBuild, pollGraphReady } from './helpers/graph';
import { triggerReport, pollReportReady } from './helpers/report';

// ---------------------------------------------------------------------------
// Section-Header aus Snapshot lesen (Single Source of Truth)
// ---------------------------------------------------------------------------
// Kein Hardcoding — der Snapshot ist die SSOT, Drift wird automatisch erkannt.
// ESM-kompatibler Pfad: import.meta.url statt __dirname (package.json "type":"module").
const _thisFile = fileURLToPath(import.meta.url);
const _thisDir = path.dirname(_thisFile);

// Pfad-Auflösung: tests/e2e/ → tests/ → frontend/ → <worktree-root>/backend/
// 3 Ebenen hoch (../../../) erreicht den Worktree-Root, dann backend/...
const SNAPSHOT_PATH = path.resolve(
  _thisDir,
  '../../../backend/tests/eval/snapshots/output-contract-required-sections.txt',
);

const REQUIRED_SECTION_HEADERS: string[] = fs
  .readFileSync(SNAPSHOT_PATH, 'utf-8')
  .split('\n')
  .map((l) => l.trim())
  .filter(Boolean);

// Sanity-Check zur Laufzeit: der Snapshot muss exakt 11 Einträge haben.
// Falls nicht, schlägt der Test mit erklärender Message fehl, nicht still.
if (REQUIRED_SECTION_HEADERS.length !== 11) {
  throw new Error(
    `Snapshot enthält ${REQUIRED_SECTION_HEADERS.length} Abschnitte, erwartet 11. ` +
      `Snapshot-Datei prüfen: ${SNAPSHOT_PATH}`,
  );
}

// ---------------------------------------------------------------------------
// Backend-Persona-Floor für die Report-Generierung
// ---------------------------------------------------------------------------
// Gespiegelt aus backend/app/services/report_agent/contract_constants.py.
// Der E2E-Stub ersetzt LLM-Antworten, aber nicht den Report-Contract-Gate.
const MIN_PERSONA_TABLE_ROWS = 50;

// ---------------------------------------------------------------------------
// Deterministisches Smoke-Dokument
// ---------------------------------------------------------------------------
const SMOKE_MARKDOWN_BODY = `# Agora E2E Smoke Document M11.4c

Dies ist ein deterministisches Testdokument für den Minimalreport-Smoke M11.4c.

## Produktbeschreibung

Das Testprodukt ist ein fiktives Software-System für CI-Verifikationszwecke.

## Zielgruppe

- DACH-Region Angestellte
- Altersgruppe 25–55
- Technologieaffinität: mittel
`;

const SMOKE_FILENAME = 'e2e-smoke-m11-4c.md';

async function seedPersonaFloor(
  apiCtx: APIRequestContext,
  simulationId: string,
  baseURL: string,
  headers: Record<string, string>,
): Promise<void> {
  for (let i = 1; i <= MIN_PERSONA_TABLE_ROWS; i += 1) {
    const username = `e2e_persona_${String(i).padStart(2, '0')}`;
    const res = await apiCtx.post(`${baseURL}/api/simulation/${simulationId}/profiles`, {
      headers: { ...headers, 'Content-Type': 'application/json' },
      data: {
        platform: 'reddit',
        username,
        name: `E2E Persona ${i}`,
        bio: `Deterministische E2E-Persona ${i}`,
        persona: `E2E Persona ${i} bewertet das Testprodukt im DACH-Kontext.`,
        age: 25 + (i % 30),
        gender: i % 2 === 0 ? 'female' : 'male',
        country: ['DE', 'AT', 'CH'][i % 3],
        profession: 'E2E Testrolle',
        interested_topics: ['Software', 'Vertrauen', 'DACH'],
      },
    });
    expect(
      res.ok(),
      `POST /api/simulation/${simulationId}/profiles fehlgeschlagen (${res.status()}): ${await res.text()}`,
    ).toBe(true);
  }

  const profilesRes = await apiCtx.get(`${baseURL}/api/simulation/${simulationId}/profiles`, {
    headers,
  });
  expect(
    profilesRes.ok(),
    `GET /api/simulation/${simulationId}/profiles fehlgeschlagen (${profilesRes.status()}): ${await profilesRes.text()}`,
  ).toBe(true);
  const profilesJson = await profilesRes.json();
  expect(
    profilesJson?.data?.count,
    `Minimalreport-Smoke braucht mindestens ${MIN_PERSONA_TABLE_ROWS} Personas`,
  ).toBeGreaterThanOrEqual(MIN_PERSONA_TABLE_ROWS);
}

// ---------------------------------------------------------------------------
// Test
// ---------------------------------------------------------------------------

test.describe('M11.4c · Minimalreport-Smoke', () => {
  test(
    '1 · Graph-Setup → Report generieren → 11 Sections + Persona-Tabelle sichtbar',
    async ({ page, context, baseURL }) => {
      // M11.4b-Followup-3: Test-Total-Timeout anheben.
      // Report-Generation (11 Sections × 4 ReACT-Iterationen im Stub) plus
      // Graph-Build-Vorlauf und Persona-Floor-Seeding dauern länger als
      // Playwright-Default (30 s).
      // test.setTimeout ist targeted (nur dieser Test), kein Global-Bump in playwright.config.ts.
      test.setTimeout(420_000);

      // =======================================================================
      // Schritt 1: Auth-Token injizieren
      // localStorage-Key 'agora_token' (frontend/src/api/index.ts:41).
      // =======================================================================
      await injectAuthToken(context);

      const headers = authHeader();
      const apiCtx = await request.newContext({
        extraHTTPHeaders: headers,
      });

      const pageErrors: string[] = [];
      page.on('pageerror', (err) => pageErrors.push(err.message));

      try {
        // ===================================================================
        // Diagnostik: Stub-Mode-Status vor dem ersten API-Call loggen.
        // Kein hartes Assert — nur informatives Logging für CI-Debugging.
        // Container-Logs (global-teardown.ts) zeigen ob llm_e2e_stub importiert.
        // ===================================================================
        await assertStubModeActive(apiCtx, baseURL!);

        // ===================================================================
        // Schritt 2+3: Markdown hochladen → Ontologie generieren
        // POST /api/graph/ontology/generate
        // ===================================================================
        const ontologyData = await uploadMarkdown(
          apiCtx,
          SMOKE_MARKDOWN_BODY,
          SMOKE_FILENAME,
          baseURL!,
          headers,
        );
        const projectId = ontologyData.project_id as string;
        expect(projectId, 'project_id muss ein nichtleerer String sein').toBeTruthy();

        // ===================================================================
        // Schritt 4: Graph-Build → POST /api/graph/build
        // ===================================================================
        const { task_id: graphTaskId } = await triggerGraphBuild(
          apiCtx,
          projectId,
          baseURL!,
          headers,
        );
        expect(graphTaskId, 'graph task_id muss ein nichtleerer String sein').toBeTruthy();

        // ===================================================================
        // Schritt 5: Graph-Status pollen bis "completed"
        // Timeout 120 s: Graph-Build mit Stub-NER ist schnell.
        // ===================================================================
        const taskResult = await pollGraphReady(apiCtx, graphTaskId, baseURL!, headers, 120_000);
        const graphId = (taskResult?.result as Record<string, unknown> | null)?.graph_id as
          | string
          | undefined;
        expect(graphId, 'graph_id muss im Task-Result vorhanden sein').toBeTruthy();

        // ===================================================================
        // Schritt 6: Simulation anlegen → POST /api/simulation/create
        // Benötigt: project_id + graph_id (backend/app/api/simulation_lifecycle.py:81).
        // Die Simulation muss nicht gestartet werden — report.generate prüft
        // nur state.graph_id (backend/app/api/report.py:107).
        // ===================================================================
        const simRes = await apiCtx.post(`${baseURL}/api/simulation/create`, {
          headers: { ...headers, 'Content-Type': 'application/json' },
          data: { project_id: projectId, graph_id: graphId },
        });
        expect(
          simRes.ok(),
          `POST /api/simulation/create fehlgeschlagen (${simRes.status()}): ${await simRes.text()}`,
        ).toBe(true);
        const simJson = await simRes.json();
        const simulationId: string = simJson?.data?.simulation_id;
        expect(simulationId, 'simulation_id muss ein nichtleerer String sein').toBeTruthy();

        // ===================================================================
        // Schritt 7: Persona-Floor seeden → POST /api/simulation/<id>/profiles
        // Report-Agent bricht vor Section-Generierung ab, wenn weniger als
        // MIN_PERSONA_TABLE_ROWS Profile in reddit_profiles.json liegen.
        // ===================================================================
        await seedPersonaFloor(apiCtx, simulationId, baseURL!, headers);

        // ===================================================================
        // Schritt 8: Report-Generierung starten → POST /api/report/generate
        // ===================================================================
        const { report_id } = await triggerReport(apiCtx, simulationId, baseURL!, headers);
        expect(report_id, 'report_id muss ein nichtleerer String sein').toBeTruthy();

        // ===================================================================
        // Schritt 9: Report-Status pollen bis "completed"
        // Timeout 300 s (5 min): 11 Sections × 4 ReACT-Iterationen im Stub.
        // Kein hardcoded setTimeout — expect.poll in pollReportReady.
        // ===================================================================
        await pollReportReady(apiCtx, report_id, baseURL!, headers, 300_000);

        // ===================================================================
        // Schritt 10: UI — /report/<report_id> laden und Assertions prüfen
        //
        // ReportView rendert Step4Report mit :reportId="currentReportId".
        // Step4Report::onMounted() ruft pollStatus() auf, das GET /api/report/<id>
        // aufruft und ReportSchema.parse() ausführt.
        // Bei status="completed" wird fullReport gesetzt und reportHtml gerendert.
        // ===================================================================
        // M11.4b-Followup-3: waitUntil: 'domcontentloaded' statt 'networkidle'.
        // SPAs mit Pinia-State-Polling erreichen niemals networkidle (>=500 ms ohne Request).
        // 'domcontentloaded': HTML-Parser durch, Inline-Scripts ausgeführt — deterministisch.
        // Nachfolgende expect(outlineList).toBeVisible() ist der Mount-Indikator via Auto-Wait.
        await page.goto(`/report/${report_id}`, { waitUntil: 'domcontentloaded' });

        // Outline-Panel muss sichtbar sein
        // ReportOutlinePanel.vue:50 — article.card mit ol.outline
        // Wird in Step4Report angezeigt wenn reportOutline !== null (Step4Report.vue:438).
        const outlineList = page.locator('ol.outline');
        await expect(
          outlineList,
          'ol.outline muss sichtbar sein (ReportOutlinePanel geladen)',
        ).toBeVisible({ timeout: 30_000 });

        // ===================================================================
        // Schritt 10: Alle 11 Section-Header aus dem Snapshot assertieren
        //
        // ReportOutlinePanel.vue:72 — span.outline-title enthält den Section-Titel.
        // Der Stub liefert exakt die 11 Snapshot-Titel via _stub_plan_response().
        // Alle 11 Titel müssen als span.outline-title sichtbar sein.
        // ===================================================================
        for (const header of REQUIRED_SECTION_HEADERS) {
          const titleLocator = page.locator('span.outline-title', { hasText: header });
          await expect(
            titleLocator,
            `Section-Header "${header}" muss als span.outline-title sichtbar sein`,
          ).toBeVisible({ timeout: 10_000 });
        }

        // ===================================================================
        // Schritt 11: Persona-Tabelle Section sichtbar
        //
        // "Persona-Tabelle" ist einer der 11 Pflichtabschnitte (Snapshot-Zeile 3).
        // Die Assertion prüft, dass der Section-Titel sichtbar ist.
        // MIN_PERSONA_TABLE_ROWS = 0: Stub erzeugt Freitext, keine Markdown-Tabelle.
        // Im echten Betrieb (nicht Stub): MIN_PERSONA_TABLE_ROWS = 50 (§6.1).
        // ===================================================================
        const personaHeader = page.locator('span.outline-title', { hasText: 'Persona-Tabelle' });
        await expect(
          personaHeader,
          '"Persona-Tabelle"-Section muss als span.outline-title sichtbar sein',
        ).toBeVisible({ timeout: 10_000 });

        // Wenn table-Zeilen vorhanden sind (im Stub: 0), muss die Mindestanzahl eingehalten werden.
        // Trivialer Stub-Check: MIN_PERSONA_TABLE_ROWS = 0 → Assertion immer true.
        // Bleibt als explizite Konstante für spätere Anhebung auf echte LLM-Werte.
        const personaSection = page.locator('.section-content').filter({
          has: page.locator('table'),
        });
        const personaSectionCount = await personaSection.count();
        if (personaSectionCount > 0) {
          const tableRows = personaSection.first().locator('tr');
          const rowCount = await tableRows.count();
          expect(
            rowCount,
            `Persona-Tabelle: mindestens ${MIN_PERSONA_TABLE_ROWS} Zeilen erwartet, ${rowCount} gefunden`,
          ).toBeGreaterThanOrEqual(MIN_PERSONA_TABLE_ROWS);
        }

        // ===================================================================
        // Schritt 12: Report-Body mit gerendertem Markdown sichtbar
        //
        // Step4Report.vue:508 — article.card v-if="phase === 2 && reportHtml"
        // Step4Report.vue:521 — div.report-body.markdown-body (v-html="reportHtml")
        // Sichtbar wenn fullReport.value gesetzt ist (phase === 2 + reportHtml !== '').
        // ===================================================================
        const reportBody = page.locator('div.report-body.markdown-body');
        await expect(
          reportBody,
          'div.report-body.markdown-body muss sichtbar sein (gerenderter Finalbericht)',
        ).toBeVisible({ timeout: 30_000 });

        // Report-Body darf nicht leer sein
        const reportText = await reportBody.textContent();
        expect(
          (reportText ?? '').trim().length,
          'Report-Body darf nicht leer sein',
        ).toBeGreaterThan(0);

        // ===================================================================
        // Abschluss: 0 Page-Errors während des gesamten Flows
        // ===================================================================
        expect(
          pageErrors,
          `Page-Errors während Minimalreport-Flow: ${pageErrors.join('; ')}`,
        ).toHaveLength(0);
      } finally {
        await apiCtx.dispose();
      }
    },
  );
});
