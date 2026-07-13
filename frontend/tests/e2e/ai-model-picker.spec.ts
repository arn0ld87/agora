/**
 * AiModelPicker — Playwright-E2E (Sub-Slice 5.6 final).
 *
 * Stand: 2026-07-13 — echte Browser-Runs (Skip-Annotationen entfernt).
 *
 * Stack (siehe global-setup.ts + scripts/e2e-up.sh):
 *   - Compose-Override haengt einen `mock-models` nginx-Service ein, der
 *     `GET /models` mit `{"data":[{"id":"qwen2.5:14b"},{"id":"gpt-oss-20b"}]}`
 *     bedient (OpenAI-kompatibel).
 *   - global-setup seeded zwei Provider-Connections:
 *       openai_compatible (online)  → http://mock-models         (2 Modelle)
 *       openai            (offline) → nicht aufloesbarer DNS-Name (0 Modelle)
 *   - Backend-Capability-Inference existiert nicht (adapters._ai_model
 *     setzt keine Capabilities → alle 'unknown'). Der chat-mode behandelt
 *     'unknown' als geeignet und filtert nur explizit 'unsupported' aus
 *     (siehe AiModelPicker.vue filteredOptions, Slice 5.6).
 *
 * Ziel-View: /settings/llm-routing (RunLlmRoutingPanel mountet pro Stage
 * einen AiModelPicker). Run-ID wird ins Run-ID-Feld eingetragen; das
 * Backend synthetisiert fuer unbekannte run_ids einen Default-Config
 * (RuntimeRunConfig.load_config braucht keinen RunRegistry-Eintrag),
 * sodass PATCH mit einer festen Test-run_id funktioniert.
 *
 * Selektor-Pfad: ausschliesslich data-testid (keine Klassen-/ARIA-/
 * i18n-Selektoren). Siehe helpers/aiModelPicker.ts + contracts/testIds.ts.
 */
import { test, expect } from '@playwright/test'
import {
  login,
  getStagePicker,
  getPickerInput,
  getPickerSearch,
  getOption,
  getGroupByConnectionId,
  openPicker,
  selectOptionByClick,
  drillKeyboard,
  readSelectedLabel,
} from './helpers/aiModelPicker'
import { LlmRoutingTestId } from './helpers/testIds'

const E2E_RUN_ID = 'run_e2e_model_picker'
const STAGE = 'document_ingest'
const ONLINE_CONN = 'openai_compatible'
const OFFLINE_CONN = 'openai'
const ONLINE_MODEL = 'qwen2.5:14b'
const OTHER_MODEL = 'gpt-oss-20b'

test.describe('Slice 5.6 · AiModelPicker E2E', () => {
  test.beforeEach(async ({ page, context }) => {
    // Single-User-Token-Mode: Token-Inject in localStorage.
    await login(context)
    await page.goto('/settings/llm-routing', { waitUntil: 'domcontentloaded' })
    // Run-ID eintragen → RunLlmRoutingPanel mountet (v-if selectedRunIdTrimmed).
    await page.getByTestId(LlmRoutingTestId.runId).fill(E2E_RUN_ID)
    // Warten bis der Stage-Picker fuer document_ingest gerendert ist.
    await expect(getStagePicker(page, STAGE)).toBeVisible()
  })

  // -------------------------------------------------------------------------
  // 1) Tastatur-Navigation ↓↓↑Enter
  // -------------------------------------------------------------------------
  test('↓↓↑Enter navigiert die Combobox und committet die Auswahl', async ({ page }) => {
    const picker = getStagePicker(page, STAGE)
    await openPicker(page, picker)

    // Warten bis die Discovery-Modelle geladen sind (Option sichtbar),
    // sonst hat ↓↓↑Enter keine Liste zum Navigieren.
    await expect(
      getOption(page, { providerConnectionId: ONLINE_CONN, modelId: OTHER_MODEL }),
    ).toBeVisible()

    const input = getPickerInput(page, picker)
    await expect(input).toBeEnabled()

    // ↓↓↑Enter: ↓ markiert 1. (gpt-oss-20b, alphabetisch zuerst), ↓ 2.
    // (qwen2.5:14b), ↑ zurueck auf 1., Enter committed.
    await drillKeyboard(page, picker)

    const label = await readSelectedLabel(page, picker)
    expect(label.length).toBeGreaterThan(0)
  })

  // -------------------------------------------------------------------------
  // 2) Suche filtert Optionen
  // -------------------------------------------------------------------------
  test('Suche filtert die Optionen auf Treffer', async ({ page }) => {
    const picker = getStagePicker(page, STAGE)
    await openPicker(page, picker)

    const search = getPickerSearch(page)
    await expect(search).toBeVisible()
    await search.fill('qwen')

    // 'qwen' matcht model_id 'qwen2.5:14b', nicht 'gpt-oss-20b'.
    await expect(
      getOption(page, { providerConnectionId: ONLINE_CONN, modelId: ONLINE_MODEL }),
    ).toBeVisible()
    await expect(
      getOption(page, { providerConnectionId: ONLINE_CONN, modelId: OTHER_MODEL }),
    ).toHaveCount(0)
  })

  // -------------------------------------------------------------------------
  // 3) Online-Modell ist verfuegbar (data-status=available, nicht disabled)
  // -------------------------------------------------------------------------
  test('Online-Modell ist verfuegbar und auswaehlbar', async ({ page }) => {
    const picker = getStagePicker(page, STAGE)
    await openPicker(page, picker)

    const onlineOption = getOption(page, { providerConnectionId: ONLINE_CONN, modelId: ONLINE_MODEL })
    await expect(onlineOption).toBeVisible()
    // data-status="available" (Quelle: AiModelPicker.vue :data-status="item.status").
    await expect(onlineOption).toHaveAttribute('data-status', 'available')
    // Nicht disabled → auswaehlbar (isDisabled filtert unavailable/unsupported).
    await expect(onlineOption).toBeEnabled()
  })

  // -------------------------------------------------------------------------
  // 4) Provider offline: keine Gruppe / keine Option (Discovery schlägt fehl)
  // -------------------------------------------------------------------------
  test('Offline-Connection liefert keine Modelle (keine Gruppe, keine Option)', async ({ page }) => {
    const picker = getStagePicker(page, STAGE)
    await openPicker(page, picker)

    // Warten bis die Online-Gruppe da ist (stellt sicher, dass die
    // Discovery ueberhaupt zurueckgekehrt ist), bevor auf Abwesenheit
    // der Offline-Gruppe assertiert wird.
    await expect(
      getGroupByConnectionId(page, ONLINE_CONN),
    ).toBeVisible()

    // Offline-Connection: Probe schlägt fehl → 0 Modelle → keine Gruppe.
    await expect(
      getGroupByConnectionId(page, OFFLINE_CONN),
    ).toHaveCount(0)
    // Keine Option aus der Offline-Connection.
    await expect(
      getOption(page, { providerConnectionId: OFFLINE_CONN, modelId: 'any' }),
    ).toHaveCount(0)
  })

  // -------------------------------------------------------------------------
  // 5) Run-Snapshot: Auswahl landet im canonical ai_route (PATCH-Response)
  // -------------------------------------------------------------------------
  test('Stage-Override landet im ai_route (source=stage_override)', async ({ page }) => {
    const picker = getStagePicker(page, STAGE)
    await openPicker(page, picker)

    // Warten bis die Option verfuegbar ist, dann per Klick auswaehlen.
    await selectOptionByClick(
      page,
      { providerConnectionId: ONLINE_CONN, modelId: ONLINE_MODEL },
      picker,
    )

    // Auswahl setzt routing.stage_overrides[document_ingest] → der
    // Apply-Button (v-if) rendert. PATCH
    // /api/runs/<run_id>/llm-routing/stages/<stage_id> liefert im
    // Response-Body das canonical ai_route-Feld (PR #700, source=stage_override).
    const applyButton = page.locator(
      `[data-testid="${LlmRoutingTestId.stageSave}"][data-stage="${STAGE}"]`,
    )

    const [response] = await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes(`/llm-routing/stages/${STAGE}`) &&
          resp.request().method() === 'PATCH',
      ),
      applyButton.click(),
    ])

    expect(response.ok()).toBe(true)
    const body = (await response.json()) as {
      data?: { ai_route?: { provider_connection_id?: string; model_id?: string; source?: string } }
      ai_route?: { provider_connection_id?: string; model_id?: string; source?: string }
    }
    // Tolerante Huelle (json_success schachtelt unter 'data').
    const aiRoute = body.data?.ai_route ?? body.ai_route
    expect(aiRoute).toBeDefined()
    expect(aiRoute?.provider_connection_id).toBe(ONLINE_CONN)
    expect(aiRoute?.model_id).toBe(ONLINE_MODEL)
    expect(aiRoute?.source).toBe('stage_override')
  })
})
