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
import { test, expect, request, type Page } from '@playwright/test';
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
import { checkTabOrder } from './helpers/tabOrder';
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
    // Etappe 2 des Frontend-Umbaus (#1797): /dashboard, /runs und /ablage sind
    // Weiterleitungen auf die Bibliothek der Läufe (siehe „Alte Adressen
    // leiten um“ unten). Die Gates laufen an den Zielen, jeder Fall an einer
    // anderen Ansicht der Bibliothek bzw. der Aktivität.
    test('Bibliothek Läufe (ehemals Dashboard) passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/library/runs');
    });

    test('Bibliothek Läufe „Läuft“ (ehemals Runs) passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/library/runs?view=running');
    });

    // Block B3 — die neue Huelle. Geprueft wird der Leerzustand (ohne
    // Backend-Daten) — fuer die Gates reicht das: sie messen Struktur, Fokus
    // und Kontrast, nicht Inhalt.
    test('Bibliothek Läufe „Mit Bericht“ (ehemals Ablage) passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/library/runs?view=with-report');
    });
  });

  // Etappe 2 (#1797): die neuen Ansichten ohne Parameter-Bedarf.
  test.describe('Bibliothek und Aktivität (Etappe 2, #1797)', () => {
    test('Bibliothek Läufe „Braucht Aufmerksamkeit“ passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/library/runs?view=attention');
    });

    test('Bibliothek Graphen passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/library/graphs');
    });

    test('Neuer Lauf passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/library/runs/new');
    });

    test('Aktivität Jobs passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/activity/jobs');
    });

    test('Aktivität Protokoll passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/activity/log');
    });
  });

  // Etappe 2 (#1797): gespeicherte Links auf alte Adressen funktionieren
  // weiter. Geprüft wird die Weiterleitung selbst (URL), nicht der Inhalt.
  test.describe('Alte Adressen leiten um (Etappe 2, #1797)', () => {
    test('/dashboard leitet auf /library/runs um', async ({ page }) => {
      await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
      await expect(page).toHaveURL(/\/library\/runs$/);
    });

    test('/runs/<id> leitet auf /activity/jobs/<id> um', async ({ page }) => {
      await page.goto('/runs/run_e2e_redirect', { waitUntil: 'domcontentloaded' });
      await expect(page).toHaveURL(/\/activity\/jobs\/run_e2e_redirect$/);
    });
  });

  test.describe('Settings', () => {
    test('Settings General passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/settings/general');
    });

    // Etappe 3 (#1799): die alten Einstellungsadressen sind Weiterleitungen auf
    // die Abschnitte des Einstellungsfensters; die Gates laufen an den Zielen.
    test('Settings Pipeline (ehemals Integrations) passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/settings/pipeline');
    });

    test('Settings Zugang (ehemals Profile, API Keys, Audit Logs) passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/settings/access');
    });

    test('Settings Anbieter (ehemals LLM Providers) passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/settings/providers');
    });

    test('Settings Embedding passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/settings/embedding');
    });
  });

  // Etappe 3 (#1799): gespeicherte Links auf die alten Einstellungs- und
  // Startadressen funktionieren weiter. Geprüft wird die Weiterleitung (URL).
  test.describe('Alte Einstellungsadressen leiten um (Etappe 3, #1799)', () => {
    const redirects: Array<[string, RegExp]> = [
      ['/settings/integrations', /\/settings\/pipeline$/],
      ['/settings/profile', /\/settings\/access$/],
      ['/settings/users-teams', /\/settings\/access$/],
      ['/settings/api-keys', /\/settings\/access$/],
      ['/settings/audit-logs', /\/settings\/access$/],
      ['/settings/llm-routing', /\/settings\/profiles$/],
      ['/settings/llm-providers', /\/settings\/providers$/],
      ['/workspace/provider-keys', /\/settings\/providers$/],
      ['/settings-classic', /\/settings\/general$/],
    ];
    for (const [from, target] of redirects) {
      test(`${from} leitet um`, async ({ page }) => {
        await page.goto(from, { waitUntil: 'domcontentloaded' });
        await expect(page).toHaveURL(target);
      });
    }
  });

  // Etappe 3 (#1799): Einstellungsfenster und Startdialog sind modale Dialoge
  // über der zuletzt gezeigten Ansicht. Geprüft: axe ohne Verstöße, Fokus im
  // Dialog, Esc schließt und kehrt zur Ansicht darunter zurück.
  test.describe('Fenster über der Ansicht (Etappe 3, #1799)', () => {
    const windows: Array<{ name: string; opener: (page: Page) => Promise<void>; testId: string; url: RegExp }> = [
      {
        name: 'Einstellungsfenster',
        opener: async (page) => {
          await page.getByRole('link', { name: 'Einstellungen', exact: true }).click();
        },
        testId: 'settings-window',
        url: /\/settings\/general$/,
      },
      {
        name: 'Startdialog Neuer Lauf',
        opener: async (page) => {
          await page.getByTestId('topbar-new-run').click();
        },
        testId: 'new-run-dialog',
        url: /\/library\/runs\/new$/,
      },
    ];

    for (const w of windows) {
      test(`${w.name}: modaler Dialog mit Fokus, ohne axe-Verstöße, Esc kehrt zurück`, async ({ page }) => {
        // Ansicht darunter: die Graphen-Bibliothek, erreicht ohne Fenster.
        await page.goto('/library/graphs', { waitUntil: 'domcontentloaded' });
        await w.opener(page);
        await expect(page).toHaveURL(w.url);

        const dialog = page.getByTestId(w.testId);
        await expect(dialog).toBeVisible();
        await expect(page.getByRole('dialog')).toHaveCount(1);

        // Fokus liegt im Dialog.
        await expect.poll(() => dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true);

        // axe: keine schweren oder kritischen Verstöße (Seite inklusive Dialog).
        const axeResults = await runAxe(page);
        assertNoCriticalViolations(axeResults);

        // Tab bleibt im Dialog (Fokusfalle).
        for (let i = 0; i < 6; i += 1) {
          await page.keyboard.press('Tab');
        }
        await expect.poll(() => dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true);

        // Esc schließt und führt zur Ansicht darunter.
        await page.keyboard.press('Escape');
        await expect(page.getByRole('dialog')).toHaveCount(0);
        await expect(page).toHaveURL(/\/library\/graphs$/);
      });
    }
  });

  test.describe('Onboarding', () => {
    test('Onboarding passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/onboarding');
    });
  });

  test.describe('Picker', () => {
    test('AiModelPicker in LLM Routing passes accessibility gates', async ({ page }) => {
      // Picker benötigt Run-ID für RunLlmRoutingPanel
      await page.goto('/settings/profiles', { waitUntil: 'domcontentloaded' });
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

      // Tab-Reihenfolge (Issue #1088)
      await checkTabOrder(page);

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

    // /v4/history leitet seit Etappe 2 auf die Aktivität um; das Gate prüft
    // die Jobliste der Aktivität (vorher: die Ablage).
    test('Verlauf (ehemals /v4/history, jetzt Aktivität Jobs) passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/activity/jobs');
    });

    // RunDetailView (frontend/src/views/RunDetailView.vue:66 — role="alert" im
    // Error-Zweig) rendert für eine unbekannte Run-ID einen strukturell
    // vollständigen, zugänglichen Fehlerzustand statt leer zu bleiben oder zu
    // crashen. Ein echter Run wäre nur über einen vollständigen Simulationslauf
    // erreichbar (siehe Ausnahme-Begründung unten) — für das reine A11y-Gate
    // (Struktur/Fokus/Kontrast, kein Inhaltstest) reicht der deterministische
    // Fehlerzustand aus und hält die Smoke-Laufzeit niedrig.
    test('Job-Detail (unbekannte Run-ID, deterministischer Fehlerzustand) passes accessibility gates', async ({
      page,
    }) => {
      await checkAccessibilityGate(page, '/activity/jobs/run_e2e_a11y_missing');
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
      await checkAccessibilityGate(page, `/compare/${simulationId}`);
    });

    // Etappe 2 (#1797): Lauf-Arbeitsbereich und Graph-Ansichten mit echter ID.
    test('Lauf Übersicht passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, `/simulations/${simulationId}`);
    });

    test('Lauf Graph passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, `/simulations/${simulationId}/graph`);
    });

    test('Graph der Bibliothek passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, `/graphs/${projectId}`);
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
