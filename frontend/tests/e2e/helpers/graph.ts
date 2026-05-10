import type { APIRequestContext } from '@playwright/test';
import { expect } from '@playwright/test';

/**
 * Startet den Graph-Build-Job via POST /api/graph/build.
 *
 * Verifiziert gegen backend/app/api/graph.py::build_graph (Zeilen 293–573).
 * Erwartet: { project_id } im JSON-Body.
 * Liefert: { task_id, project_id, run_id, message } aus dem json_success-Envelope.
 *
 * Setzt AGORA_E2E_LLM_MODE=stub voraus — die LLM-Calls in OntologyGenerator
 * (ontology/generate) und NERExtractor (add_text) laufen deterministisch durch.
 */
export async function triggerGraphBuild(
  ctx: APIRequestContext,
  projectId: string,
  baseURL: string,
  authHeader: Record<string, string>,
): Promise<{ task_id: string; run_id: string }> {
  const res = await ctx.post(`${baseURL}/api/graph/build`, {
    headers: { ...authHeader, 'Content-Type': 'application/json' },
    data: { project_id: projectId },
  });

  if (!res.ok()) {
    const text = await res.text();
    throw new Error(
      `triggerGraphBuild: POST /api/graph/build fehlgeschlagen (${res.status()}): ${text}`,
    );
  }

  const json = await res.json();
  const task_id: string = json?.data?.task_id;
  if (!task_id) {
    throw new Error(
      `triggerGraphBuild: Antwort enthält kein task_id. Body: ${JSON.stringify(json)}`,
    );
  }
  return { task_id, run_id: json?.data?.run_id ?? '' };
}

/**
 * Pollt GET /api/graph/task/<task_id> bis status "completed" oder "failed".
 *
 * Verifiziert gegen backend/app/models/task.py::TaskStatus:
 *   PENDING="pending", PROCESSING="processing", COMPLETED="completed", FAILED="failed"
 *
 * Verwendet expect.poll() — kein hardcoded setTimeout/waitForTimeout.
 * Timeout über Playwright-Default (30 s) hinaus konfigurierbar via pollTimeout-Param.
 */
export async function pollGraphReady(
  ctx: APIRequestContext,
  taskId: string,
  baseURL: string,
  authHeader: Record<string, string>,
  pollTimeout: number = 120_000,
): Promise<Record<string, unknown>> {
  let lastBody: Record<string, unknown> = {};

  await expect
    .poll(
      async () => {
        const res = await ctx.get(`${baseURL}/api/graph/task/${taskId}`, {
          headers: authHeader,
        });
        if (!res.ok()) return 'http_error';
        const json = await res.json();
        lastBody = (json?.data ?? {}) as Record<string, unknown>;
        return lastBody.status;
      },
      {
        message: `Graph-Task ${taskId} hat "completed" nicht innerhalb des Timeouts erreicht`,
        timeout: pollTimeout,
        intervals: [500, 1000, 2000, 3000],
      },
    )
    .toBe('completed');

  return lastBody;
}
