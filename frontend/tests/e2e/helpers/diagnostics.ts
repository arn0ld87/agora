import { expect, type APIRequestContext } from '@playwright/test';
import { authHeader } from './auth';

/**
 * Stellt sicher, dass der Backend-Container im E2E-Stub-Modus läuft.
 *
 * Fragt `GET /api/status` ab und assertiert hart auf `e2e.stub_active`. Dieses
 * Feld stammt aus `AGORA_E2E_LLM_MODE` im **Backend-Prozess** — derselben
 * Variable, die `LLMClient.chat_json` auswertet, bevor es den Provider-Call
 * überspringt.
 *
 * Vorher las diese Funktion `process.env.AGORA_E2E_LLM_MODE` aus dem
 * *Playwright*-Prozess, kehrte bei `!res.ok()` früh zurück und verschluckte
 * jeden Fehler im catch. Sie hat damit nichts zugesichert: eine Suite konnte
 * grün durchlaufen, obwohl das Backend gegen einen echten Provider lief. Fünf
 * Specs (run-budget, minimal-report, golden-gate-accessibility, report-modes,
 * upload-graph) hingen an dieser Zusicherung.
 *
 * Wirft, wenn der Stub nicht aktiv ist — ein Lauf ohne Stub ist kein
 * Diagnose-Hinweis, sondern ein ungültiger Lauf.
 *
 * Der Auth-Header wird hier selbst gesetzt und nicht vom Aufrufer erwartet:
 * `/api/status` ist authentifiziert, aber nur drei der fünf Specs bauen ihren
 * Context mit `extraHTTPHeaders: authHeader()` — `report-modes.spec.ts:148`
 * und `golden-gate-accessibility.spec.ts:180` übergeben einen nackten Context.
 * Solange der frühe Return existierte, fiel das nicht auf; der 401 wurde
 * stillschweigend als „Stub aktiv" durchgewunken. Ein Header auf Request-Ebene
 * ist gegenüber `extraHTTPHeaders` des Contexts additiv, deshalb bleiben die
 * drei bereits authentifizierten Aufrufer unverändert korrekt.
 *
 * @param apiCtx  Playwright APIRequestContext (Auth-Header optional)
 * @param baseURL Backend-Basis-URL (z. B. http://127.0.0.1:80)
 */
export async function assertStubModeActive(
  apiCtx: APIRequestContext,
  baseURL: string,
): Promise<void> {
  console.log('[diagnostics] Stub-Mode-Check via GET /api/status ...');

  const res = await apiCtx.get(`${baseURL}/api/status`, {
    headers: authHeader(),
    // 10 s Timeout — Status-Endpoint sollte sofort antworten
    timeout: 10_000,
  });
  expect(
    res.ok(),
    `GET /api/status antwortete ${res.status()} — Stack nicht bereit, Stub-Mode nicht pruefbar.`,
  ).toBe(true);

  const json = await res.json();
  // json_success legt die Felder top-level ab; ältere Aufrufer erwarteten
  // teilweise die data-Verschachtelung — beide Formen werden akzeptiert.
  const root = json?.data ?? json;

  const backendOk: boolean = root?.backend?.ok === true;
  const version: string = root?.backend?.version ?? 'unbekannt';
  const neo4jReachable: boolean = root?.neo4j?.reachable === true;
  console.log(
    `[diagnostics] Backend: ok=${backendOk}, version=${version}, neo4j_reachable=${neo4jReachable}`,
  );

  const e2e = root?.e2e;
  expect(
    e2e,
    'GET /api/status liefert keinen e2e-Teilbaum. Backend-Image ist aelter als der '
      + 'SystemStatusE2E-Contract — Stack neu bauen.',
  ).toBeDefined();

  console.log(
    `[diagnostics] Backend AGORA_E2E_LLM_MODE=${e2e?.llm_mode ?? '<nicht gesetzt>'}, `
      + `stub_active=${e2e?.stub_active}`,
  );

  expect(
    e2e?.stub_active,
    `Backend laeuft NICHT im E2E-Stub-Modus (llm_mode=${e2e?.llm_mode ?? '<nicht gesetzt>'}). `
      + 'Die Suite wuerde gegen einen echten LLM-Provider laufen; das ist kein gueltiger E2E-Lauf. '
      + 'AGORA_E2E_LLM_MODE=stub im Backend-Container setzen.',
  ).toBe(true);
}
