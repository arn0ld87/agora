import type { APIRequestContext } from '@playwright/test';

/**
 * Prüft ob der Backend-Container im E2E-Stub-Modus läuft.
 *
 * Fragt GET /api/status ab und dumpt den AGORA_E2E_LLM_MODE-Hinweis aus den
 * Container-Logs auf stdout. Da /api/status die env-Variable nicht direkt
 * exponiert, ist diese Funktion absichtlich nur informativ (kein hartes assert).
 *
 * Container-Logs zeigen beim Modulimport von llm_e2e_stub:
 *   INFO agora.llm_e2e_stub: Modul importiert. AGORA_E2E_LLM_MODE=stub ...
 *
 * Das garantiert, dass der Stub aktiv ist — auch wenn /api/status keine
 * explizite Stub-Indikator-Spalte hat.
 *
 * @param apiCtx  Playwright APIRequestContext (mit Auth-Header)
 * @param baseURL Backend-Basis-URL (z. B. http://127.0.0.1:80)
 */
export async function assertStubModeActive(
  apiCtx: APIRequestContext,
  baseURL: string,
): Promise<void> {
  console.log('[diagnostics] Stub-Mode-Check via GET /api/status ...');
  try {
    const res = await apiCtx.get(`${baseURL}/api/status`, {
      // 10 s Timeout — Status-Endpoint sollte sofort antworten
      timeout: 10_000,
    });
    if (!res.ok()) {
      console.warn(
        `[diagnostics] GET /api/status antwortete ${res.status()} — Stack evtl. nicht bereit.`,
      );
      return;
    }
    const json = await res.json();
    // backend.ok muss true sein
    const backendOk: boolean = json?.backend?.ok === true || json?.data?.backend?.ok === true;
    const version: string = json?.backend?.version ?? json?.data?.backend?.version ?? 'unbekannt';
    const neo4jReachable: boolean =
      json?.neo4j?.reachable === true || json?.data?.neo4j?.reachable === true;

    console.log(
      `[diagnostics] Backend: ok=${backendOk}, version=${version}, neo4j_reachable=${neo4jReachable}`,
    );

    // AGORA_E2E_LLM_MODE ist in /api/status nicht direkt sichtbar.
    // Die Aktivierung wird beim Container-Start via llm_e2e_stub-Logging belegt
    // (Container-Logs in global-teardown.ts gesammelt).
    // Hier nur informatives Logging — kein hartes Assert, um den Test nicht
    // zu brechen wenn /api/status noch kein stub_mode-Feld hat.
    const stubModeHint: string = process.env.AGORA_E2E_LLM_MODE ?? '<nicht im Playwright-Env>';
    console.log(
      `[diagnostics] AGORA_E2E_LLM_MODE im Playwright-Prozess: ${stubModeHint}`,
    );
    console.log(
      '[diagnostics] Stub-Aktivierung im Container via llm_e2e_stub-Logging in Container-Logs (global-teardown.ts) bestätigen.',
    );
  } catch (err) {
    console.error('[diagnostics] GET /api/status fehlgeschlagen (non-fatal):', err);
  }
}
