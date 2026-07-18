/**
 * P4.4 · E2E-Smokes für Report-Modi (strict/balanced/explorative)
 *
 * Setzt PLAN.md §5.4 um. Drei Smokes plus ein Default-Test:
 *   1. Pro Modus einen Report triggern (`force_regenerate=true`, sonst würde
 *      `_can_reuse_existing_report` (api/report.py) den zweiten und dritten
 *      Trigger als Cache-Hit zurückgeben).
 *   2. Pro Report den Mode-Banner im Markdown-Export prüfen
 *      (Quelle: backend/app/services/report_agent/markdown_renderer.py::_MODE_BANNER).
 *
 * Vertrags-Anker:
 *   - Backend liest `?mode=strict|balanced|explorative` als Query-Param
 *     (backend/app/api/report.py::_resolve_report_mode, Zeile 83).
 *   - Default ohne Param: "balanced" (DEFAULT_REPORT_MODE in report_v3.py:34).
 *   - Markdown-Banner: konstanter Prefix "**Report-Modus:**" + Modus-Name
 *     (markdown_renderer.py::_MODE_BANNER).
 *
 * Warum kein JSON-Assert auf `report_mode`? Der `?format=json`-Branch in
 * `api/report.py` baut `ReportContractModel` (v2-Envelope, schema_version=2)
 * und das v2-Modell hat kein `report_mode`-Feld — das lebt nur auf ReportV3.
 * Der Markdown-Banner ist die einzige durch den Export beobachtbare Wirkung
 * von `report_mode` und damit der korrekte Smoke-Anker.
 *
 * Stub-Modus-Begründung: AGORA_E2E_LLM_MODE=stub deterministisch — keine
 * echten LLM-Calls, kein Netz. Pro Modus Build-Zeit ca. 30–90 s im Stub
 * (analog minimal-report.spec.ts).
 *
 * Root-Cause-Korrektur (verifiziert 2026-07-18, Issue #739 Sub-Slice 4):
 * `beforeAll` legte bislang KEINE Personas an. `generate_report()`
 * (backend/app/services/report_agent/workflow.py::_load_persona_count vs.
 * _load_persona_floor) bricht dann vor jeder Section-Generierung mit
 * `ReportStatus.INCOMPLETE` ab — `ReportGenerationService.run_generate()`
 * meldet das an den Run-Registry als "failed" (nicht "processing"/"hängend").
 * pollReportReady erreicht "completed" folglich NIE, unabhängig vom
 * Test-Timeout. Fix: exakt dieselbe Persona-Floor-Seed-Strategie wie
 * minimal-report.spec.ts (Commit a2935b02, "seed personas for minimal
 * report smoke") — 50 Stub-Profile via POST /api/simulation/<id>/profiles
 * vor dem ersten triggerReport-Aufruf.
 */

import { test, expect, request, type APIRequestContext } from '@playwright/test';
import { authHeader } from './helpers/auth';
import { assertStubModeActive } from './helpers/diagnostics';
import { uploadMarkdown } from './helpers/upload';
import { triggerGraphBuild, pollGraphReady } from './helpers/graph';
import { triggerReport, pollReportReady } from './helpers/report';

// ---------------------------------------------------------------------------
// Backend-Persona-Floor für die Report-Generierung
// ---------------------------------------------------------------------------
// Gespiegelt aus backend/app/services/report_agent/contract_constants.py.
// Der E2E-Stub ersetzt LLM-Antworten, aber nicht den Report-Contract-Gate
// (workflow.py::_load_persona_count / _load_persona_floor).
const MIN_PERSONA_TABLE_ROWS = 50;

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
    `Report-Modes-Smoke braucht mindestens ${MIN_PERSONA_TABLE_ROWS} Personas`,
  ).toBeGreaterThanOrEqual(MIN_PERSONA_TABLE_ROWS);
}

// ---------------------------------------------------------------------------
// Mode-Banner-Erwartungen
// ---------------------------------------------------------------------------
// Quelle: backend/app/services/report_agent/markdown_renderer.py::_MODE_BANNER
// Wir prüfen pro Modus zwei Marker: das fixe Prefix und den Modus-Namen.
// Die genaue Beschreibung ("Nur belegte Claims …") kann sich später ändern,
// ohne diesen Smoke zu brechen — eine strengere Snapshot-Bindung gehört in
// einen Backend-Test (`tests/eval/snapshots/`).
const MODE_BANNER_PREFIX = '**Report-Modus:**';

const MODES = ['strict', 'balanced', 'explorative'] as const;

// ---------------------------------------------------------------------------
// Shared Setup
// ---------------------------------------------------------------------------

interface SharedFixture {
  baseURL: string;
  authHeaders: Record<string, string>;
  simulationId: string;
}

let shared: SharedFixture | null = null;

// Deterministisches Smoke-Dokument für den Upload-Vorlauf (analog
// minimal-report.spec.ts::SMOKE_MARKDOWN_BODY).
const SMOKE_MARKDOWN_BODY = `# Agora E2E Smoke Document P4.4

Drei-Modi-Smoke-Test (strict/balanced/explorative) gegen die Report-Pipeline.

## Produktbeschreibung

Testprodukt für die Mode-Banner-Verdrahtung (PLAN.md §5.1/§5.4).

## Zielgruppe

- DACH-Region Angestellte
- Altersgruppe 30–55
`;
const SMOKE_FILENAME = 'e2e-smoke-p4-4.md';

test.beforeAll(async () => {
  // Graph-Build-Vorlauf + 50 sequenzielle Persona-Seed-Requests (Root-Cause-
  // Fix, s. Dateikopf) überschreiten den Playwright-Default von 30_000ms.
  // test.setTimeout() wirkt hier auf den aktuell laufenden Hook (beforeAll),
  // analog zur Test-Body-Nutzung in minimal-report.spec.ts:177.
  test.setTimeout(180_000);

  const baseURL = process.env.AGORA_E2E_BASE_URL ?? 'http://127.0.0.1:80';
  const ctx = await request.newContext({ baseURL });
  const headers = authHeader();

  await assertStubModeActive(ctx, baseURL);

  // Upload + Graph-Vorlauf — exakt analog minimal-report.spec.ts.
  const ontologyData = await uploadMarkdown(
    ctx,
    SMOKE_MARKDOWN_BODY,
    SMOKE_FILENAME,
    baseURL,
    headers,
  );
  const projectId = ontologyData.project_id as string;
  if (!projectId) {
    throw new Error(`project_id fehlt in Ontology-Response: ${JSON.stringify(ontologyData)}`);
  }

  const { task_id: graphTaskId } = await triggerGraphBuild(ctx, projectId, baseURL, headers);
  const taskResult = await pollGraphReady(ctx, graphTaskId, baseURL, headers);
  const graphId = (taskResult?.result as Record<string, unknown> | null)?.graph_id as
    | string
    | undefined;
  if (!graphId) {
    throw new Error(`graph_id fehlt im Task-Result: ${JSON.stringify(taskResult)}`);
  }

  // Simulation anlegen — braucht project_id + graph_id.
  const simRes = await ctx.post(`${baseURL}/api/simulation/create`, {
    headers: { ...headers, 'Content-Type': 'application/json' },
    data: {
      project_id: projectId,
      graph_id: graphId,
      target_audience: 'p4-4 mode smokes',
    },
  });
  if (!simRes.ok()) {
    throw new Error(
      `Simulation-Create fehlgeschlagen (${simRes.status()}): ${await simRes.text()}`,
    );
  }
  const simJson = await simRes.json();
  const simulationId: string = simJson?.data?.simulation_id;
  if (!simulationId) {
    throw new Error(`simulation_id fehlt in Response: ${JSON.stringify(simJson)}`);
  }

  // Persona-Floor seeden — sonst bricht generate_report() vor jeder
  // Section-Generierung mit ReportStatus.INCOMPLETE ab (s. Root-Cause-
  // Kommentar am Dateikopf).
  await seedPersonaFloor(ctx, simulationId, baseURL, headers);

  shared = { baseURL, authHeaders: headers, simulationId };
  await ctx.dispose();
});

// ---------------------------------------------------------------------------
// Mode-Tests (sequentiell)
// ---------------------------------------------------------------------------
//
// `test.describe.serial` stellt sicher, dass die Modi nacheinander laufen.
// Bei `force_regenerate=true` darf ein parallel laufender Modus nicht
// eingreifen — der Report-Manager schreibt sonst überlappende Status-Files
// für dieselbe simulation_id.

test.describe.serial('report modes', () => {
  for (const mode of MODES) {
    test(`mode=${mode} liefert passenden Mode-Banner im Markdown`, async () => {
      // Root-Cause (verifiziert via CI-Logs 2026-07-18, Issue #739 Sub-Slice 4):
      // Playwright-Test-Default-Timeout ist 30_000ms — pollReportReady's
      // eigener pollTimeout (300_000ms) greift NIE, weil der äußere
      // Test-Timeout die Ausführung längst abbricht. Stub-Report-Build
      // (11 Sections × ReACT-Runden, ggf. + Quote-Repair-Retry) dauert
      // 30–90s+ (s. Datei-Header). Analog M11.4b-Followup-3
      // (minimal-report.spec.ts:177) und upload-graph.spec.ts:67.
      test.setTimeout(420_000);

      // shared ist nach beforeAll gesetzt; bei beforeAll-Fehler startet
      // Playwright diesen Test gar nicht erst.
      const { baseURL, authHeaders, simulationId } = shared!;
      const ctx = await request.newContext({ baseURL });
      try {
        const { report_id } = await triggerReport(
          ctx,
          simulationId,
          baseURL,
          authHeaders,
          { mode, forceRegenerate: true },
        );
        await pollReportReady(ctx, report_id, baseURL, authHeaders);

        const mdRes = await ctx.get(
          `${baseURL}/api/report/${report_id}/export?format=md`,
          { headers: authHeaders },
        );
        expect(
          mdRes.ok(),
          `MD-Export für ${report_id} fehlgeschlagen (${mdRes.status()})`,
        ).toBeTruthy();
        const md = await mdRes.text();
        expect(
          md,
          `Mode-Banner-Prefix "${MODE_BANNER_PREFIX}" fehlt im Markdown für mode=${mode}`,
        ).toContain(MODE_BANNER_PREFIX);
        expect(
          md,
          `Modus-Name "${mode}" fehlt im Markdown-Banner für mode=${mode}`,
        ).toContain(mode);
      } finally {
        await ctx.dispose();
      }
    });
  }

  // Default-Verhalten: kein mode-Param → balanced. Eigenständiger Test, damit
  // ein Default-Drift (z. B. von "balanced" auf "strict") nicht in den
  // mode=balanced-Lauf einsickert und unbemerkt bleibt.
  test('ohne mode-Param Default = balanced', async () => {
    // Gleiche Root-Cause wie oben — siehe Kommentar bei den Mode-Tests.
    test.setTimeout(420_000);

    const { baseURL, authHeaders, simulationId } = shared!;
    const ctx = await request.newContext({ baseURL });
    try {
      const { report_id } = await triggerReport(
        ctx,
        simulationId,
        baseURL,
        authHeaders,
        { forceRegenerate: true }, // kein mode → Default
      );
      await pollReportReady(ctx, report_id, baseURL, authHeaders);
      const mdRes = await ctx.get(
        `${baseURL}/api/report/${report_id}/export?format=md`,
        { headers: authHeaders },
      );
      expect(mdRes.ok()).toBeTruthy();
      const md = await mdRes.text();
      expect(md).toContain(MODE_BANNER_PREFIX);
      expect(md).toContain('balanced');
    } finally {
      await ctx.dispose();
    }
  });
});
