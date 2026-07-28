/**
 * Slice 7.2 — Golden-Gate Accessibility Gates.
 *
 * Wiederverwendbare Playwright-Gates für Shell, Settings, Onboarding und Picker.
 * Prüft pro Route:
 * - axe-core ohne serious/critical violations
 * - 320×800 Viewport ohne horizontales Dokument-Scrollen
 * - Tastaturbedienung (Tab-Navigation)
 * - Focus sichtbar (:focus-visible)
 * - Reduced Motion (prefers-reduced-motion: reduce)
 *
 * Stack: Playwright + axe-core (siehe global-setup.ts + scripts/e2e-up.sh).
 * Auth: Single-User-Token-Mode via localStorage (siehe helpers/auth.ts).
 */
import { test, request } from '@playwright/test';
import { injectAuthToken, authHeader } from './helpers/auth';
import { ensureOnboardingDismissed } from './helpers/onboarding';
import {
  checkAccessibilityGate,
  runAxe,
  assertNoCriticalViolations,
  check320pxNoHorizontalScroll,
  checkKeyboardNavigation,
  checkFocusVisible,
  checkReducedMotion,
} from './helpers/accessibility';
import { LlmRoutingTestId } from './helpers/testIds';
import { assertStubModeActive } from './helpers/diagnostics';
import { uploadMarkdown } from './helpers/upload';
import { triggerGraphBuild, pollGraphReady } from './helpers/graph';

// Issue #838 — deterministisches Smoke-Dokument für die v4-Step-Routen-Gates.
// Analog zu minimal-report.spec.ts / upload-graph.spec.ts, aber ohne
// Report-Generierung (kein Persona-Floor, kein 300s-Poll) — die a11y-Gates
// prüfen nur Struktur/Fokus/Kontrast, nicht den Inhalt.
const A11Y_SMOKE_MARKDOWN_BODY = `# Agora Golden-Gate A11y Smoke Document

Deterministisches Testdokument für die Router-/A11y-Regressionstests aus Issue #838.

## Zielgruppe

- DACH-Region, Angestellte, Technologieaffinität mittel.
`;
const A11Y_SMOKE_FILENAME = 'e2e-golden-gate-a11y.md';

test.describe('Slice 7.2 · Golden-Gate Accessibility Gates', () => {
  test.beforeEach(async ({ context, page }) => {
    await injectAuthToken(context);
    // Cross-Cutting-Fund Issue #739 Sub-Slice 5/5: onboardingGuard redirected
    // sonst jede Route auf /onboarding — axe-core würde nur die
    // Onboarding-Seite prüfen statt der Zielroute.
    await ensureOnboardingDismissed(page);
  });

  test.describe('Shell', () => {
    test('Dashboard passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/dashboard');
    });

    test('Runs passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/runs');
    });
  });

  test.describe('Settings', () => {
    test('Settings General passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/settings/general');
    });

    test('Settings Integrations passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/settings/integrations');
    });

    test('Settings Profile passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/settings/profile');
    });

    test('Settings API Keys passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/settings/api-keys');
    });

    test('Settings LLM Providers passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/settings/llm-providers');
    });

    test('Settings Embedding passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/settings/embedding');
    });
  });

  test.describe('Onboarding', () => {
    test('Onboarding passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/onboarding');
    });
  });

  test.describe('Picker', () => {
    test('AiModelPicker in LLM Routing passes accessibility gates', async ({ page }) => {
      // Picker benötigt Run-ID für RunLlmRoutingPanel
      await page.goto('/settings/llm-routing', { waitUntil: 'domcontentloaded' });
      await page.getByTestId(LlmRoutingTestId.runId).fill('run_e2e_accessibility');

      // Warte bis Picker gerendert ist
      await page.getByTestId('ai-model-picker').first().waitFor({ timeout: 5000 });

      // axe-core
      const axeResults = await runAxe(page);
      assertNoCriticalViolations(axeResults);

      // 320px
      await check320pxNoHorizontalScroll(page);

      // Reset viewport
      await page.setViewportSize({ width: 1280, height: 720 });

      // Keyboard
      await checkKeyboardNavigation(page);

      // Focus visible
      await checkFocusVisible(page);

      // Reduced motion
      await checkReducedMotion(page);
    });
  });

  // Issue #838 — Golden-Gate-Abgleich gegen die konsolidierte Routenliste
  // (ADR-0010). Ergänzt die bisher fehlenden Routen ohne Parameter-Bedarf.
  test.describe('Zusätzliche Shell-/Settings-Routen (Issue #838)', () => {
    // /home ist per #915 (ADR-0010) ein Redirect auf /dashboard und damit
    // keine eigenständig gate-fähige Route mehr. Das Golden-Gate deckt
    // die kanonische Route /dashboard (siehe describe-Block oben) ab, die
    // weiterhin gegatet ist. Issue #920 (320px-Mangel in Home.vue) wird
    // gegenstandslos, da Home.vue nicht mehr produktiv geroutet wird.

    test('Settings Audit Logs passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/settings/audit-logs');
    });

    test('History (v4) passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/v4/history');
    });

    // RunDetailView (frontend/src/views/RunDetailView.vue:66 — role="alert" im
    // Error-Zweig) rendert für eine unbekannte Run-ID einen strukturell
    // vollständigen, zugänglichen Fehlerzustand statt leer zu bleiben oder zu
    // crashen. Ein echter Run wäre nur über einen vollständigen Simulationslauf
    // erreichbar (siehe Ausnahme-Begründung unten) — für das reine A11y-Gate
    // (Struktur/Fokus/Kontrast, kein Inhaltstest) reicht der deterministische
    // Fehlerzustand aus und hält die Smoke-Laufzeit niedrig.
    test('Run Detail (unbekannte Run-ID, deterministischer Fehlerzustand) passes accessibility gates', async ({
      page,
    }) => {
      await checkAccessibilityGate(page, '/runs/run_e2e_a11y_missing');
    });
  });

  // Issue #838 — v4-Step-Routen mit echter Projekt-/Simulations-ID.
  // Setup wiederverwendet dieselben Seams wie upload-graph.spec.ts /
  // minimal-report.spec.ts (helpers/upload.ts, helpers/graph.ts), aber OHNE
  // Report-Generierung: kein Persona-Floor-Seeding, kein 300s-Status-Poll.
  // Die a11y-Gates prüfen nur Struktur/Fokus/Kontrast der Shell, nicht den
  // Simulations-/Report-Inhalt — ein Graph-Build (Sekunden im Stub-Modus)
  // genügt, um eine echte projectId/simulationId zu erzeugen.
  test.describe('v4-Step-Routen (echte Projekt-/Simulations-ID, Issue #838)', () => {
    let projectId = '';
    let simulationId = '';

    test.beforeAll(async () => {
      // Upload + Graph-Build-Vorlauf überschreiten den Playwright-Default von
      // 30_000ms. test.setTimeout() wirkt auf den laufenden Hook — exakt das
      // Muster aus report-modes.spec.ts:140-145.
      test.setTimeout(180_000);

      // baseURL wird bewusst NICHT als Fixture destrukturiert: `baseURL` ist
      // test-scoped und in einem beforeAll-Hook nicht auflösbar. Bestehende
      // Specs lesen es deshalb aus der Umgebung (report-modes.spec.ts:147).
      const baseURL = process.env.AGORA_E2E_BASE_URL ?? 'http://127.0.0.1:80';
      const headers = authHeader();
      const apiCtx = await request.newContext({ baseURL });
      try {
        // Ohne Stub-Modus würde der Graph-Build echte Provider-Calls auslösen.
        await assertStubModeActive(apiCtx, baseURL);

        const ontologyData = await uploadMarkdown(
          apiCtx,
          A11Y_SMOKE_MARKDOWN_BODY,
          A11Y_SMOKE_FILENAME,
          baseURL,
          headers,
        );
        projectId = ontologyData.project_id as string;
        if (!projectId) {
          throw new Error(`project_id fehlt in Ontology-Response: ${JSON.stringify(ontologyData)}`);
        }

        const { task_id } = await triggerGraphBuild(apiCtx, projectId, baseURL, headers);
        const taskResult = await pollGraphReady(apiCtx, task_id, baseURL, headers);
        const graphId = (taskResult?.result as Record<string, unknown> | null)?.graph_id as
          | string
          | undefined;
        if (!graphId) {
          throw new Error(`graph_id fehlt im Task-Result: ${JSON.stringify(taskResult)}`);
        }

        const simRes = await apiCtx.post(`${baseURL}/api/simulation/create`, {
          headers: { ...headers, 'Content-Type': 'application/json' },
          data: { project_id: projectId, graph_id: graphId },
        });
        if (!simRes.ok()) {
          throw new Error(
            `POST /api/simulation/create fehlgeschlagen (${simRes.status()}): ${await simRes.text()}`,
          );
        }
        const simJson = await simRes.json();
        simulationId = simJson?.data?.simulation_id;
        if (!simulationId) {
          throw new Error(
            `Setup für v4-Step-Routen-Gates lieferte keine simulation_id. Body: ${JSON.stringify(simJson)}`,
          );
        }
      } finally {
        await apiCtx.dispose();
      }
    });

    test('Step Graph Build passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, `/v4/graph-build/${projectId}`);
    });

    test('Step Env Setup passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, `/v4/env-setup/${projectId}`);
    });

    test('Step Simulation passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, `/v4/simulation/${simulationId}`);
    });

    test('Step Simulation Feed passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, `/v4/simulation/${simulationId}/feed`);
    });

    test('Compare (v4) passes accessibility gates', async ({ page }) => {
      // CompareView.vue:12 zeigt bei fehlenden Branches einen role="alert"-
      // Fehlerzustand, ansonsten BranchComparePanel — beide Zweige sind
      // barrierefrei; eine frische Simulation ohne Branches deckt den
      // Fehlerzweig ab.
      await checkAccessibilityGate(page, `/v4/compare/${simulationId}`);
    });
  });

  // Issue #838 — dokumentierte Ausnahme (KEIN stilles Weglassen):
  // /v4/report/:reportId und /v4/interaction/:reportId sind bewusst NICHT
  // Teil dieses Golden-Gate-Smokes. Ein zugänglicher, vollständiger Report
  // erfordert den kompletten Report-Generierungs-Flow aus
  // minimal-report.spec.ts (Persona-Floor-Seeding mit 50 Profilen +
  // POST /api/report/generate + Status-Poll bis "completed", dort mit
  // test.setTimeout(420_000) budgetiert). Das pro Push zusätzlich zweimal
  // (Report- und Interaction-Route) im a11y-Gate zu wiederholen, würde die
  // Golden-Gate-Laufzeit um mehrere Minuten pro Lauf erhöhen, ohne neue
  // Strukturaussagen zu liefern — StepReportView/StepInteractionView teilen
  // sich dieselbe AppShell/PageHeader-Struktur, die bereits über die anderen
  // v4-Step-Routen in diesem Gate abgedeckt ist (AppShell-Navigation,
  // Fokus-Reihenfolge, Reduced-Motion). Ein synthetischer/unbekannter
  // reportId-Wert wurde bewusst NICHT verwendet, weil Step4Report (anders als
  // RunDetailView/CompareView/StepGraphBuildView) keinen verifizierten
  // barrierefreien Fehlerzustand für eine nicht existierende reportId zeigt
  // — das würde faktisch einen ungetesteten Codepfad pinnen statt eine echte
  // Garantie treffen. Sollte der Report-Flow künftig einen günstigeren
  // Fixture-Seam bekommen (z.B. Report-Fixture-Import statt Voll-Generierung),
  // ist das der Anschlusspunkt, um diese Ausnahme aufzulösen.
});
