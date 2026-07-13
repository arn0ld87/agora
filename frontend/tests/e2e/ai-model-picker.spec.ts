/**
 * AiModelPicker — Playwright-E2E (Sub-Slice 5.6-Prep).
 *
 * Stand: 2026-07-13 — SKELETON. Der gesamte describe-Block ist mit
 * `test.describe.skip()` markiert, weil die Komponente noch in KEINER
 * produktiven View gemountet ist. Sub-Slice 5.4 (Migration der
 * Auswahlstellen) liefert die Views; 5.6 final muss dann nur die
 * `.skip`-Annotation entfernen und ggf. Selektor-Pfade an die
 * konkret migrierten Routen anpassen.
 *
 * Aktivierung pro Test:
 *
 *   1) Tastatur-Navigation ↓↓↑Enter
 *      Voraussetzung: 5.4 hat AiModelPicker in mindestens einer
 *      Settings/Dashboard-View gemountet (Empfehlung slice-5:
 *      SettingsGeneralView). 5.6 final: `await page.goto('/settings/general')`
 *      o. ae. statt des hier dokumentierten `goto`/Stub.
 *
 *   2) Provider offline
 *      Voraussetzung: Backend liefert im Test-Fixture mindestens
 *      einen Provider mit status='unavailable' (siehe useAvailableModels
 *      Composable + ProviderConnectionStore). 5.6 final: Seed im
 *      global-setup oder ein dedizierter Test-Helper-Endpoint.
 *
 *   3) Run-Snapshot
 *      Voraussetzung: 5.4 hat die Stage-Override-UI auf AiModelPicker
 *      umgestellt (z. B. in LlmRoutingView.vue) UND 5.3 (PR #700) ist
 *      gemergt — AiRoute ist im Endpoint
 *      GET /api/runs/<run_id>/llm-routing verfuegbar.
 *
 * Helper: siehe frontend/tests/e2e/helpers/aiModelPicker.ts.
 * testId-SSoT: frontend/src/contracts/testIds.ts.
 *
 * Out of Scope hier: 5.4 (Migration), 5.5 (Deprecation). Die Spec
 * ist absichtlich eng am 5.6-Sub-Plan-Scope gehalten, damit sie
 * nicht versehentlich Migrations-Logik mitverifiziert.
 */
import { test, expect, request, type APIRequestContext } from '@playwright/test'
import {
  login,
  getPicker,
  getPickerInput,
  getPickerSearch,
  getOption,
  getGroupByConnectionId,
  openPicker,
  selectOptionByClick,
  drillKeyboard,
  readSelectedLabel,
} from './helpers/aiModelPicker'
import { authHeader } from './helpers/auth'

// 5.4: aktivieren sobald die Komponente in mindestens einer View gemountet ist.
test.describe.skip('Slice 5.6 · AiModelPicker E2E', () => {
  test.beforeEach(async ({ page, context }) => {
    // Single-User-Token-Mode (siehe health.spec.ts Test 4): kein
    // klassisches Login, sondern Token-Inject in localStorage.
    await login(context)
    // 5.4 muss diese Route in App.vue (oder dem Hash-Router) registrieren.
    // Solange 5.4 offen ist, fuehrt goto() in einen 404 — daher der skip.
    await page.goto('/settings/general', { waitUntil: 'domcontentloaded' })
  })

  // -------------------------------------------------------------------------
  // 1) Tastatur-Navigation ↓↓↑Enter
  // -------------------------------------------------------------------------
  test.describe('Tastatur-Navigation', () => {
    test('↓↓↑Enter oeffnet Combobox, wandert Auswahl und committed', async ({ page }) => {
      const picker = getPicker(page)
      await expect(picker).toBeVisible()

      // 1. Trigger-Input ist fokussierbar.
      const input = getPickerInput(page, picker)
      await expect(input).toBeVisible()
      await expect(input).toBeEnabled()

      // 2. ↓↓↑Enter: reka-ui Combobox-Logik navigiert ueber die
      //    sichtbaren Items. Nach ↓↓↑ ist das 2. Item aktiv
      //    (initial ↓ markiert 1., ↓ markiert 2., ↑ geht zurueck auf 1.).
      //    Enter committed den Eintrag.
      await drillKeyboard(page, picker)

      // 3. Nach Enter: Trigger-Input zeigt das gewaehlte Modell.
      //    (Konkrete Erwartung wird in 5.6 final gesetzt, sobald die
      //    Seed-Daten aus useAvailableModels feststehen.)
      const label = await readSelectedLabel(page, picker)
      expect(label.length).toBeGreaterThan(0)
      // 5.4: aktiveren, sobald SettingsGeneralView den Picker nutzt.
    })

    test('Suche filtert Optionen, Pfeile wandern ueber Treffer', async ({ page }) => {
      const picker = getPicker(page)
      await openPicker(page, picker)
      // reka-ui ComboboxInput im Content ist die Such-Leiste.
      const search = getPickerSearch(page, picker)
      await expect(search).toBeVisible()
      await search.fill('qwen')

      // Treffer-Liste: die als `qwen` matchenden Optionen.
      // 5.6 final: konkrete provider_connection_id aus Seed ableiten.
      const firstMatch = picker.locator('[data-testid^="ai-model-picker-option"]').first()
      await expect(firstMatch).toBeVisible()

      // 5.4: aktiveren, sobald Seed verfuegbar ist.
    })
  })

  // -------------------------------------------------------------------------
  // 2) Provider offline: Status-Badge + disabled Modell
  // -------------------------------------------------------------------------
  test.describe('Provider offline', () => {
    test('Modell mit status=unavailable hat disabled-Attribut und Status-Badge', async ({ page }) => {
      const picker = getPicker(page)
      await openPicker(page, picker)

      // 5.6 final: provider_connection_id + model_id aus dem
      // Test-Seed ableiten (Empfehlung: dedizierter
      // 'unavailable'-Provider im Test-Fixture).
      const offlineOption = getOption(
        page,
        { providerConnectionId: 'conn-offline', modelId: 'gpt-offline' },
        picker,
      )

      // a) data-status reflektiert 'unavailable' (Quelle: AiModelPicker.vue,
      //    :data-status="item.status" — schon vor diesem PR gesetzt).
      await expect(offlineOption).toHaveAttribute('data-status', 'unavailable')

      // b) ComboboxItem rendert das disabled-Attribut. reka-ui setzt
      //    zusaetzlich aria-disabled; beide sind akzeptabel.
      const ariaDisabled = await offlineOption.getAttribute('aria-disabled')
      const nativeDisabled = await offlineOption.getAttribute('data-disabled')
      expect(ariaDisabled === 'true' || nativeDisabled !== null).toBe(true)

      // c) Status-Badge ist sichtbar (reka-ui ComboboxItem ist der
      //    Traeger; Badge liegt innerhalb des Items). Text ist i18n,
      //    daher Pruefung auf Klasse ai-model-picker__badge--err.
      await expect(
        offlineOption.locator('.ai-model-picker__badge--err'),
      ).toBeVisible()

      // 5.4: aktiveren, sobald Seed einen 'unavailable'-Provider enthaelt.
    })

    test('Provider-Group rendert Status-Label im Group-Header', async ({ page }) => {
      const picker = getPicker(page)
      await openPicker(page, picker)

      const offlineGroup = getGroupByConnectionId(page, 'conn-offline', picker)
      // Group-Header enthaelt den lokalisierten Status.
      // Textuelle Assertion ist i18n-fest, daher Pruefung auf die
      // Group-Label-Klasse.
      await expect(offlineGroup.locator('.ai-model-picker__group-label')).toBeVisible()
      // 5.4: aktiveren, sobald Seed verfuegbar ist.
    })
  })

  // -------------------------------------------------------------------------
  // 3) Run-Snapshot: Auswahl landet im canonical ai_route
  // -------------------------------------------------------------------------
  test.describe('Run-Snapshot', () => {
    // 5.3 (PR #700) liefert das `ai_route`-Feld im Endpoint
    // GET /api/runs/<run_id>/llm-routing. 5.4 muss die Stage-Override-UI
    // auf AiModelPicker umgestellt haben.
    test('gewaehltes Modell landet im Run-Snapshot (ai_route)', async ({ page, baseURL }) => {
      // Bestehender Run mit laufender Stage-Override-Konfiguration.
      // 5.6 final: run_id aus einem frischen Test-Run ableiten
      // (z. B. ueber helpers/upload.ts + minimal-report.spec.ts-Pattern).
      const runId = 'run_e2e_placeholder'

      const picker = getPicker(page)
      // 5.4: Annahme — die Stage-Override-View (z. B. LlmRoutingView)
      // enthaelt den Picker pro Stage. Der Pfad muss in 5.6 final an
      // die echte Route angepasst werden.
      await page.goto(`/runs/${runId}/routing`, { waitUntil: 'domcontentloaded' })

      // 1) Auswahl via Picker treffen.
      const target = {
        providerConnectionId: 'conn-ollama-local',
        modelId: 'qwen2.5:14b',
      }
      await selectOptionByClick(page, target, picker)

      // 2) Speichern (Button-Text ist i18n; 5.6 final nutzt ein
      //    dediziertes data-testid am Save-Button, sobald 5.4 ihn
      //    umgestellt hat).
      // await page.getByTestId('stage-override-save').click()

      // 3) Run-Snapshot-Endpoint pruefen.
      //    GET /api/runs/<run_id>/llm-routing liefert seit PR #700
      //    das canonical `ai_route`-Feld (AiRoute-Schema, siehe
      //    backend/app/contracts/ai_provider_contract.py).
      const ctx: APIRequestContext = await request.newContext({
        extraHTTPHeaders: authHeader(),
      })
      const res = await ctx.get(`${baseURL}/api/runs/${runId}/llm-routing`)
      expect(res.ok()).toBe(true)

      const body = (await res.json()) as { data?: { ai_route?: { provider_connection_id?: string; model_id?: string; source?: string } } }
      const route = body.data?.ai_route
      expect(route).toBeDefined()
      expect(route?.provider_connection_id).toBe(target.providerConnectionId)
      expect(route?.model_id).toBe(target.modelId)
      // Source ist seit 5.3 'stage-override' (siehe slice-5-subplan §5.3).
      expect(route?.source).toBe('stage-override')

      await ctx.dispose()
      // 5.4: aktiveren, sobald Stage-Override-View den Picker nutzt
      //       UND 5.3 in main gemergt ist (PR #700).
    })
  })
})
