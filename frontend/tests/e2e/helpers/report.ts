import type { APIRequestContext } from '@playwright/test';
import { expect } from '@playwright/test';

/**
 * Startet die Report-Generierung via POST /api/report/generate.
 *
 * Verifiziert gegen backend/app/api/report.py::generate_report (Zeile 74).
 * Erwartet: { simulation_id } im JSON-Body.
 * Liefert: { report_id, task_id, run_id } aus dem json_success-Envelope.
 *
 * Setzt voraus:
 * - simulation_id zeigt auf eine existierende Simulation mit graph_id
 *   (backend/app/api/report.py:107 — "Missing graph ID" schlägt sonst an).
 * - AGORA_E2E_LLM_MODE=stub — LLM-Calls laufen deterministisch durch.
 */
export async function triggerReport(
  ctx: APIRequestContext,
  simulationId: string,
  baseURL: string,
  authHeader: Record<string, string>,
  options: { mode?: 'strict' | 'balanced' | 'explorative'; forceRegenerate?: boolean } = {},
): Promise<{ report_id: string; task_id: string; run_id: string }> {
  // mode wandert als Query-Parameter, force_regenerate in den Body — exakte
  // Vertragsentsprechung zu backend/app/api/report.py::_resolve_report_mode
  // (request.args.get("mode")) und ::generate_report (data.get("force_regenerate")).
  const url = options.mode
    ? `${baseURL}/api/report/generate?mode=${options.mode}`
    : `${baseURL}/api/report/generate`;
  const body: Record<string, unknown> = { simulation_id: simulationId };
  if (options.forceRegenerate) body.force_regenerate = true;
  const res = await ctx.post(url, {
    headers: { ...authHeader, 'Content-Type': 'application/json' },
    data: body,
  });

  if (!res.ok()) {
    const text = await res.text();
    throw new Error(
      `triggerReport: POST /api/report/generate fehlgeschlagen (${res.status()}): ${text}`,
    );
  }

  const json = await res.json();
  const report_id: string = json?.data?.report_id;
  const task_id: string = json?.data?.task_id;
  if (!report_id) {
    throw new Error(
      `triggerReport: Antwort enthält kein report_id. Body: ${JSON.stringify(json)}`,
    );
  }
  return { report_id, task_id: task_id ?? '', run_id: json?.data?.run_id ?? '' };
}

/**
 * Terminale Statuswerte, die kein Erfolg sind (backend/app/models/report.py::
 * ReportStatus, backend/app/services/report_status.py:96-108). "incomplete"
 * ist seit #1277-2 ein bewusster dritter Endzustand — Backend, Zod-Contract
 * (reportContract.ts), useReportGeneration.ts und Step4Report.vue tragen ihn
 * alle mit. Ein Report, der hier landet, wird nie mehr "completed".
 */
const TERMINAL_FAILURE_STATUSES = new Set(['incomplete', 'failed']);

function describeTerminalFailure(reportId: string, body: Record<string, unknown>): string {
  const parts = [`Report ${reportId} hat einen terminalen Status erreicht, der kein Erfolg ist: "${String(body.status)}".`];
  if (body.error) parts.push(`error: ${String(body.error)}`);
  if (Array.isArray(body.run_degradations) && body.run_degradations.length > 0) {
    parts.push(`run_degradations: ${JSON.stringify(body.run_degradations)}`);
  }
  if (Array.isArray(body.missing_sections) && body.missing_sections.length > 0) {
    parts.push(`missing_sections: ${JSON.stringify(body.missing_sections)}`);
  }
  return parts.join(' ');
}

/**
 * Pollt POST /api/report/generate/status bis status "completed" ist.
 *
 * Verifiziert gegen backend/app/api/report.py::get_generate_status (Zeile 226).
 * Erwartet: { report_id } im JSON-Body.
 *
 * Verwendet expect.poll() — kein hardcoded setTimeout/waitForTimeout. Wirft
 * bei einem terminalen Nicht-Erfolgsstatus (s. TERMINAL_FAILURE_STATUSES)
 * sofort statt bis zum Timeout zu warten: ein solcher Status ändert sich
 * nicht mehr, jede weitere Sekunde Polling ist verschwendete Wartezeit, kein
 * zusätzliches Signal (#1387). Das macht den Test strenger, nicht toleranter
 * — "incomplete" gilt weiterhin nicht als Erfolg, der Test schlägt fehl,
 * nur schneller und mit einer Begründung statt eines bloßen Timeouts.
 * expect.poll() propagiert einen im Generator geworfenen Fehler sofort nach
 * oben, statt ihn als "noch kein Treffer" zu werten und weiterzupollen.
 *
 * Statuswerte (backend/app/services/report_agent/manager.py::ReportStatus):
 *   "pending" | "planning" | "generating" | "completed" | "incomplete" | "failed"
 *
 * Im Stub-Modus dauert der Report-Build ca. 30–90 s (11 Sections × 4 ReACT-Runden).
 * Daher Timeout 300 s (5 min) als Standard — analog der Aufgabenstellung.
 */
export async function pollReportReady(
  ctx: APIRequestContext,
  reportId: string,
  baseURL: string,
  authHeader: Record<string, string>,
  pollTimeout: number = 300_000,
): Promise<Record<string, unknown>> {
  let lastBody: Record<string, unknown> = {};

  await expect
    .poll(
      async () => {
        const res = await ctx.post(`${baseURL}/api/report/generate/status`, {
          headers: { ...authHeader, 'Content-Type': 'application/json' },
          data: { report_id: reportId },
        });
        if (!res.ok()) return 'http_error';
        const json = await res.json();
        lastBody = (json?.data ?? {}) as Record<string, unknown>;
        const status = lastBody.status;
        if (typeof status === 'string' && TERMINAL_FAILURE_STATUSES.has(status)) {
          throw new Error(describeTerminalFailure(reportId, lastBody));
        }
        return status;
      },
      {
        message: `Report ${reportId} hat "completed" nicht innerhalb des Timeouts erreicht`,
        timeout: pollTimeout,
        intervals: [1000, 2000, 5000],
      },
    )
    .toBe('completed');

  return lastBody;
}
