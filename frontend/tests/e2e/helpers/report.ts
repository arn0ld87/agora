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
 * Pollt POST /api/report/generate/status bis status "completed" oder "failed".
 *
 * Verifiziert gegen backend/app/api/report.py::get_generate_status (Zeile 226).
 * Erwartet: { report_id } im JSON-Body.
 *
 * Verwendet expect.poll() — kein hardcoded setTimeout/waitForTimeout.
 * Timeout über Playwright-Default konfigurierbar via pollTimeout-Param.
 *
 * Statuswerte (backend/app/services/report_agent/manager.py::ReportStatus):
 *   "pending" | "planning" | "generating" | "completed" | "failed"
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
        return lastBody.status;
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
