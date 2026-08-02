/**
 * #764 · Run-Budget-Smoke
 *
 * Ablauf:
 *   1. Auth-Token injizieren (localStorage via context.addInitScript).
 *   2. Graph-Vorlauf: uploadMarkdown → triggerGraphBuild → pollGraphReady
 *      (Report-Pfad benötigt einen Graph, siehe minimal-report.spec.ts).
 *   3. Simulation anlegen + 50 Stub-Personas seeden (Persona-Floor).
 *   4. Preflight-Schätzung prüfen: POST /api/simulation/preflight-estimate
 *      liefert is_estimate=true mit ehrlichen Bereichen/Status.
 *   5. Report-Generierung mit hartem, niedrigem Testbudget starten:
 *      POST /api/report/generate { budget: { max_llm_calls: 2, enforcement: "hard" } }.
 *      Der Stub-LLM-Pfad schreibt Invocation-Events pro Call; der Enforcer
 *      blockiert den dritten Aufruf deterministisch (BudgetExceededError).
 *   6. Run pollen bis terminal. Erwartung: status="stopped" UND
 *      termination_reason="budget_calls" — kein technischer Fehler.
 *   7. Abschlussverbrauch: GET /api/runs/<id>/usage zeigt gezählte Aufrufe.
 *   8. UI: /runs/<run_id> zeigt Verbrauchsanalyse (usage-totals) und den
 *      Budgetabbruch (budget-exceeded-banner).
 *   9. Accessibility: axe ohne critical/serious, 320px ohne Horizontal-Scroll.
 *  10. 0 Page-Errors während des gesamten Flows.
 *
 * Keine echten kostenpflichtigen Provider: AGORA_E2E_LLM_MODE=stub
 * (LLMClient-Stub-Branch, siehe minimal-report.spec.ts Stub-Vertrag).
 */

import { test, expect, request, type APIRequestContext } from '@playwright/test';
import { injectAuthToken, authHeader } from './helpers/auth';
import { ensureOnboardingDismissed } from './helpers/onboarding';
import { assertStubModeActive } from './helpers/diagnostics';
import { uploadMarkdown } from './helpers/upload';
import { triggerGraphBuild, pollGraphReady } from './helpers/graph';
import { runAxe, assertNoCriticalViolations, check320pxNoHorizontalScroll } from './helpers/accessibility';

const MIN_PERSONA_TABLE_ROWS = 50;

const SMOKE_MARKDOWN_BODY = `# Agora E2E Smoke Document Run-Budget

Dies ist ein deterministisches Testdokument für den Run-Budget-Smoke (#764).

## Produktbeschreibung

Das Testprodukt ist ein fiktives Software-System für CI-Verifikationszwecke.

## Zielgruppe

- DACH-Region Angestellte
- Altersgruppe 25–55
- Technologieaffinität: mittel
`;

const SMOKE_FILENAME = 'e2e-smoke-run-budget.md';

async function seedPersonaFloor(
  apiCtx: APIRequestContext,
  simulationId: string,
  baseURL: string,
  headers: Record<string, string>,
): Promise<void> {
  for (let i = 1; i <= MIN_PERSONA_TABLE_ROWS; i += 1) {
    const res = await apiCtx.post(`${baseURL}/api/simulation/${simulationId}/profiles`, {
      headers: { ...headers, 'Content-Type': 'application/json' },
      data: {
        platform: 'reddit',
        username: `e2e_budget_persona_${String(i).padStart(2, '0')}`,
        name: `E2E Budget Persona ${i}`,
        bio: `Deterministische E2E-Persona ${i}`,
        persona: `E2E Budget Persona ${i} bewertet das Testprodukt im DACH-Kontext.`,
        age: 25 + (i % 30),
        gender: i % 2 === 0 ? 'female' : 'male',
        country: ['DE', 'AT', 'CH'][i % 3],
        profession: 'E2E Testrolle',
        interested_topics: ['Software', 'Budget', 'DACH'],
      },
    });
    expect(
      res.ok(),
      `POST /api/simulation/${simulationId}/profiles fehlgeschlagen (${res.status()}): ${await res.text()}`,
    ).toBe(true);
  }
}

test.describe('#764 · Run-Budget-Smoke', () => {
  test(
    '1 · Preflight → hartes Budget → deterministischer Budgetabbruch → Verbrauchsanalyse',
    async ({ page, context, baseURL }) => {
      // Graph-Vorlauf + Persona-Seeding + Stub-Report-Start dauern länger als
      // der Playwright-Default (30 s). Der Budgetabbruch selbst ist schnell
      // (3. LLM-Call wird blockiert) — das Timeout deckt den Vorlauf ab.
      test.setTimeout(420_000);

      await injectAuthToken(context);
      const headers = authHeader();
      const apiCtx = await request.newContext({ extraHTTPHeaders: headers });

      const pageErrors: string[] = [];
      page.on('pageerror', (err) => pageErrors.push(err.message));

      try {
        await assertStubModeActive(apiCtx, baseURL!);

        // Graph-Vorlauf
        const ontologyData = await uploadMarkdown(
          apiCtx,
          SMOKE_MARKDOWN_BODY,
          SMOKE_FILENAME,
          baseURL!,
          headers,
        );
        const projectId = ontologyData.project_id as string;
        expect(projectId).toBeTruthy();

        const { task_id: graphTaskId } = await triggerGraphBuild(
          apiCtx,
          projectId,
          baseURL!,
          headers,
        );
        const taskResult = await pollGraphReady(apiCtx, graphTaskId, baseURL!, headers, 120_000);
        const graphId = (taskResult?.result as Record<string, unknown> | null)?.graph_id as
          | string
          | undefined;
        expect(graphId, 'graph_id muss im Task-Result vorhanden sein').toBeTruthy();

        // Simulation + Persona-Floor
        const simRes = await apiCtx.post(`${baseURL}/api/simulation/create`, {
          headers: { ...headers, 'Content-Type': 'application/json' },
          data: { project_id: projectId, graph_id: graphId },
        });
        expect(
          simRes.ok(),
          `POST /api/simulation/create fehlgeschlagen (${simRes.status()}): ${await simRes.text()}`,
        ).toBe(true);
        const simulationId: string = (await simRes.json())?.data?.simulation_id;
        expect(simulationId).toBeTruthy();
        await seedPersonaFloor(apiCtx, simulationId, baseURL!, headers);

        // =============================================================
        // Schritt 4: Preflight-Schätzung (ehrlich gekennzeichnet)
        // =============================================================
        // num_agents/max_rounds MUESSEN mitgegeben werden. Der Endpunkt leitet
        // sie sonst aus dem Artefakt `simulation_config` ab — das entsteht aber
        // erst bei der Simulations-VORBEREITUNG, nicht durch
        // POST /api/simulation/create + Profil-Seeding. Ohne die beiden Felder
        // antwortet das Backend deterministisch mit HTTP 400
        // ("num_agents und max_rounds werden benötigt …",
        // backend/app/api/simulation_budget.py:140-148).
        // Befund des CI-/E2E-Audits 2026-07-31: Diese Datei lief seit PR #975
        // in keinem Workflow, deshalb blieb der Fehler unentdeckt.
        // simulation_id bleibt im Body — damit laeuft der Config-Lookup-Zweig
        // weiterhin mit (er liefert hier None und faellt auf die Direktwerte
        // zurueck), statt still einen anderen Codepfad zu testen.
        const preflightRes = await apiCtx.post(`${baseURL}/api/simulation/preflight-estimate`, {
          headers: { ...headers, 'Content-Type': 'application/json' },
          data: {
            simulation_id: simulationId,
            num_agents: MIN_PERSONA_TABLE_ROWS,
            max_rounds: 2,
          },
        });
        expect(
          preflightRes.ok(),
          `preflight-estimate fehlgeschlagen (${preflightRes.status()}): ${await preflightRes.text()}`,
        ).toBe(true);
        const estimate = (await preflightRes.json())?.data;
        expect(estimate?.is_estimate, 'Schätzung muss als Schätzung gekennzeichnet sein').toBe(true);
        expect(
          estimate?.estimated_tokens_low,
          'Preflight muss eine Token-Untergrenze liefern',
        ).toBeGreaterThan(0);
        expect(estimate?.estimated_tokens_high).toBeGreaterThanOrEqual(
          estimate?.estimated_tokens_low,
        );
        expect(['unknown', 'estimated', 'free']).toContain(estimate?.cost_status);

        // =============================================================
        // Schritt 5: Report mit hartem, niedrigem Testbudget starten
        // =============================================================
        const genRes = await apiCtx.post(`${baseURL}/api/report/generate`, {
          headers: { ...headers, 'Content-Type': 'application/json' },
          data: {
            simulation_id: simulationId,
            budget: { max_llm_calls: 2, enforcement: 'hard' },
          },
        });
        expect(
          genRes.ok(),
          `POST /api/report/generate fehlgeschlagen (${genRes.status()}): ${await genRes.text()}`,
        ).toBe(true);
        const genJson = await genRes.json();
        const runId: string = genJson?.data?.run_id;
        expect(runId, 'run_id muss ein nichtleerer String sein').toBeTruthy();

        // =============================================================
        // Schritt 6: Run pollen — deterministischer Budgetabbruch
        // =============================================================
        let finalRun: Record<string, unknown> | null = null;
        let lastKnownStatus = 'processing';
        await expect
          .poll(
            async () => {
              const res = await apiCtx.get(`${baseURL}/api/runs/${runId}`, { headers });
              // Issue #764 (Codex P1): transiente non-OK-Antworten
              // (5xx/429) duerfen NICHT den Poll beenden, sondern werden
              // wie ein "noch nicht terminal"-Status behandelt. Sonst
              // wuerde ein einzelner transienter Fehler den Test vorzeitig
              // gruen machen, obwohl der Run noch laeuft.
              if (!res.ok()) return lastKnownStatus;
              const data = (await res.json())?.data;
              if (!data || typeof data !== 'object') return lastKnownStatus;
              finalRun = data;
              lastKnownStatus =
                typeof data.status === 'string' ? data.status : lastKnownStatus;
              return lastKnownStatus;
            },
            {
              timeout: 240_000,
              intervals: [2_000, 5_000, 10_000],
              message: 'Run muss terminal enden (stopped via Budgetabbruch)',
            },
          )
          .not.toBe('processing');

        expect(finalRun, 'Run-Detail muss abrufbar sein').toBeTruthy();
        expect(
          finalRun!.status,
          `Budgetabbruch muss status=stopped liefern, nicht failed. message=${finalRun!.message}`,
        ).toBe('stopped');
        expect(
          finalRun!.termination_reason,
          'Abbruchgrund muss von technischem Fehler unterscheidbar sein',
        ).toBe('budget_calls');

        // Budgetstatus im angereicherten Detail: exceeded + Warnung vorhanden
        const budget = finalRun!.budget as
          | { status?: string; exceeded_dimension?: string; warnings?: unknown[] }
          | null
          | undefined;
        expect(budget?.status, 'Budgetstatus muss exceeded sein').toBe('exceeded');
        expect(budget?.exceeded_dimension).toBe('calls');

        // =============================================================
        // Schritt 7: Abschlussverbrauch (Teilresultate bleiben erhalten)
        // =============================================================
        const usageRes = await apiCtx.get(`${baseURL}/api/runs/${runId}/usage`, { headers });
        expect(
          usageRes.ok(),
          `GET /api/runs/<id>/usage fehlgeschlagen (${usageRes.status()}): ${await usageRes.text()}`,
        ).toBe(true);
        const usage = (await usageRes.json())?.data;
        expect(
          usage?.totals?.llm_calls,
          'Verbrauch muss die bis zum Abbruch gezählten Aufrufe zeigen',
        ).toBeGreaterThanOrEqual(1);
        expect(usage?.totals?.llm_calls).toBeLessThanOrEqual(2);

        // =============================================================
        // Schritt 8: UI — Verbrauchsanalyse + Abbruch-Banner
        // =============================================================
        // onboardingGuard (router/onboardingGuard.ts:32) redirected JEDE
        // nicht-exempte Route auf /onboarding, solange onboarding_required
        // gilt — Default-Zustand eines frischen E2E-Stacks. Ohne diesen
        // Aufruf landet page.goto('/runs/<id>') auf dem Einrichtungs-Wizard
        // und getByTestId('usage-totals') existiert schlicht nicht; der
        // DOM-Snapshot des fehlgeschlagenen CI-Laufs zeigte genau das.
        // Der Aufruf ist idempotent (onboarding_state_store.py::dismiss).
        await ensureOnboardingDismissed(page);

        await page.goto(`${baseURL}/runs/${runId}`);
        await expect(
          page.getByTestId('usage-totals'),
          'Verbrauchsanalyse (Gesamtwerte) muss sichtbar sein',
        ).toBeVisible({ timeout: 30_000 });
        await expect(
          page.getByTestId('budget-exceeded-banner'),
          'Budgetabbruch muss in der UI erkennbar sein',
        ).toBeVisible();

        // =============================================================
        // Schritt 9: Accessibility-Gates
        // =============================================================
        assertNoCriticalViolations(await runAxe(page));
        await check320pxNoHorizontalScroll(page);

        // Schritt 10: keine Page-Errors
        expect(pageErrors, 'Keine Page-Errors während des Flows').toEqual([]);
      } finally {
        await apiCtx.dispose();
      }
    },
  );
});
