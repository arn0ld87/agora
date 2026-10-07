/**
 * Fensterrouten-Navigation · Graph-Build-Smoke
 *
 * Regression für: „Neuer Lauf" → Datei + Frage → „Graph bauen" baut keinen
 * Graphen. Symptom (Stand 11318c5b, beide Deployments): Die URL wechselt auf
 * /v4/graph-build/new?maxRounds=…, der Seiteninhalt bleibt leer. Ursache war
 * die Route-Transition in App.vue mit mode="out-in": Beim Verlassen der
 * Fensterroute (meta.windowOverBackground) warf Vue in afterLeave
 * "Cannot read properties of null (reading 'parentNode')" und blieb im
 * Leave-Zustand hängen — der StepGraphBuildView mountete nie, die Pipeline
 * startete nicht (kein POST /api/graph/ontology/generate).
 *
 * Ablauf (echter Dialog-Weg, kein API-Shortcut):
 *   1. Auth-Token injizieren + Onboarding dismissen (onboardingGuard, Issue #739)
 *   2. /library/runs/new laden — Startdialog als Fensterroute über der Bibliothek
 *   3. Simulationsfrage füllen + Quelldatei in die SourceDropzone setzen
 *   4. „Graph bauen" klicken (data-testid new-run-start)
 *   5. POST /api/graph/ontology/generate MUSS gefeuert werden (Request-Spy)
 *   6. URL MUSS /v4/graph-build/<echte-project-id> sein (router.replace aus
 *      useGraphBuildPipeline.initialize nach Upload-Response)
 *   7. .pipeline-stepper MUSS sichtbar sein (StepGraphBuildView gemountet)
 *   8. Keine pageerror-Events (TypeError-Wiederkehr)
 *
 * Endpoints abgeleitet aus:
 *   - backend/app/api/graph.py::generate_ontology (POST /api/graph/ontology/generate)
 *   - frontend/src/composables/useGraphBuildPipeline.ts (Upload → project_id
 *     aus Response → router.replace auf die echte Projekt-ID)
 *
 * DOM-Selektoren abgeleitet aus:
 *   - frontend/src/components/new-run/NewRunDialog.vue (data-testid
 *     new-run-dialog, new-run-question, new-run-start; SourceDropzone rendert
 *     input[type=file])
 *   - frontend/src/views/v4/steps/StepGraphBuildView.vue (.pipeline-stepper im
 *     Step-Layout — im Broken-State mountet der View nie, der Stepper fehlt)
 */

import { test, expect, request } from '@playwright/test';
import { injectAuthToken, authHeader } from './helpers/auth';
import { assertStubModeActive } from './helpers/diagnostics';

// Deterministisches Markdown-Dokument, bewusst klein (< 500 Zeichen) damit
// der Text-Splitting-Schritt möglichst einen einzigen Chunk erzeugt.
const SMOKE_MARKDOWN_BODY = `# Agora E2E Smoke Document (Graph-Build-Navigation)

Dies ist ein deterministisches Testdokument für den Dialog-Navigations-Smoke.
Es dient ausschließlich der CI-Verifikation, dass der Weg aus dem Startdialog
in den Graph-Build tatsächlich ankommt.

## Beteiligte Akteure

- **Startdialog**: Fensterroute /library/runs/new.
- **StepGraphBuildView**: Ziel der Navigation nach „Graph bauen".
`;

const SMOKE_FILENAME = 'e2e-smoke-graph-build-navigation.md';

const SMOKE_QUESTION =
  'Wie reagieren DACH-Stakeholder auf die Einführung des simulierten Dialog-Navigations-Smokes?';

test.describe('Fensterrouten-Navigation · Graph-Build aus dem Startdialog', () => {
  test('1 · Graph bauen → View mountet, Pipeline startet, URL bekommt echte Projekt-ID', async ({
    page,
    context,
    baseURL,
  }) => {
    // Upload + Ontology + Cold-Start des Stacks können im CI länger als der
    // Playwright-Default (30 s) dauern — targeted Timeout wie in upload-graph.spec.ts.
    test.setTimeout(120_000);

    await injectAuthToken(context);
    const headers = authHeader();

    // Separater Request-Context für API-Calls (kein Browser-State)
    const apiCtx = await request.newContext({ extraHTTPHeaders: headers });

    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    try {
      // Stub-Mode-Status loggen (informativ, kein hartes Assert) — siehe
      // upload-graph.spec.ts.
      await assertStubModeActive(apiCtx, baseURL!);

      // Onboarding-Wizard wegräumen, sonst redirected der onboardingGuard
      // (router/onboardingGuard.ts) die Navigation zu /onboarding. Dismiss ist
      // idempotent — sicher bei mehrfachem Run. (Issue #739)
      const dismissRes = await apiCtx.post(`${baseURL}/api/onboarding/dismiss`, {
        headers,
      });
      expect(
        dismissRes.ok(),
        `POST /api/onboarding/dismiss fehlgeschlagen (${dismissRes.status()}): ${await dismissRes.text()}`,
      ).toBe(true);

      // Startdialog als Fensterroute öffnen. 'domcontentloaded' statt
      // 'networkidle' — SPAs mit Polling/SSE erreichen networkidle nie.
      await page.goto('/library/runs/new', {
        waitUntil: 'domcontentloaded',
        timeout: 60_000,
      });

      const dialog = page.getByTestId('new-run-dialog');
      await expect(dialog, 'Startdialog muss als Fensterroute geöffnet sein').toBeVisible({
        timeout: 30_000,
      });

      // Simulationsfrage füllen (Pflichtfeld, sonst bleibt der Start-Button
      // disabled) und Quelldatei in die SourceDropzone legen.
      await page.getByTestId('new-run-question').fill(SMOKE_QUESTION);
      await dialog.locator('input[type="file"]').setInputFiles({
        name: SMOKE_FILENAME,
        mimeType: 'text/markdown',
        buffer: Buffer.from(SMOKE_MARKDOWN_BODY, 'utf-8'),
      });

      // Neo4j-Bereitschaft und Modellliste werden beim Dialogöffnen async
      // geladen; die Blocker verschwinden danach. Auto-Wait auf enabled.
      const start = page.getByTestId('new-run-start');
      await expect(start, 'Start-Button muss nach Frage + Datei klickbar sein').toBeEnabled({
        timeout: 30_000,
      });

      // Request-Spy VOR dem Klick registrieren: Der Ontologie-Call wird erst
      // nach der erfolgreichen Navigation vom StepGraphBuildView gefeuert.
      // Das ist das Kernsymptom in umgekehrt — ohne den Navigations-Fix
      // bleibt dieser Request für immer aus.
      const ontologyRequest = page.waitForRequest(
        (req) => req.method() === 'POST' && req.url().includes('/api/graph/ontology/generate'),
        { timeout: 60_000 },
      );

      await start.click();

      await ontologyRequest;

      // Nach der Upload-Response ersetzt useGraphBuildPipeline.initialize die
      // Platzhalter-Route /v4/graph-build/new durch die echte project_id.
      await expect(page).toHaveURL(/\/v4\/graph-build\/[0-9a-f][0-9a-f-]{7,}/, {
        timeout: 60_000,
      });

      // Der StepGraphBuildView muss tatsächlich gemountet sein — im
      // Broken-State wechselt nur die URL, der View-Inhalt bleibt leer und
      // der Pipeline-Stepper taucht im DOM nie auf.
      await expect(
        page.locator('.pipeline-stepper'),
        'Pipeline-Stepper des StepGraphBuildView muss sichtbar sein',
      ).toBeVisible({ timeout: 30_000 });

      // Keine pageerror-Events während des gesamten Flows — fängt die
      // TypeError-Wiederkehr (afterLeave/null parentNode) zusätzlich ab.
      expect(
        pageErrors,
        `Page-Errors während Dialog-Navigation: ${pageErrors.join('; ')}`,
      ).toHaveLength(0);
    } finally {
      await apiCtx.dispose();
    }
  });
});