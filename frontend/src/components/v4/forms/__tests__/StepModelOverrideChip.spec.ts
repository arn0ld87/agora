/**
 * StepModelOverrideChip — Spec-Tests fuer Slice 5.4 Migration auf AiModelPicker.
 *
 * Die Komponente zeigt die effektive Modell-Route fuer eine Stage und
 * ermoeglicht per Popover den Wechsel. Migration auf AiModelPicker:
 *  - ModelPicker (alt) → AiModelPicker (SSoT aus Slice 5.1)
 *  - LlmRoute-Update → AiModelRef-Update, konvertiert via
 *    useAiModelRefAdapter.toLlmRoute fuer setStageOverride.
 *
 * Coverage:
 *  1. mountet ohne Crash
 *  2. zeigt Default-Label (prop)
 *  3. zeigt model_id aus effektiver Route
 *  4. zeigt "Modell waehlen" wenn Route kein model hat
 *  5. Klick oeffnet/schliesst Popover
 *  6. locked=true: Klick oeffnet nicht
 *  7. locked=true: Lock-Icon sichtbar
 *  8. hasOverride: Override-Badge sichtbar
 *  9. no Override: kein Badge
 * 10. AiModelPicker-Update mit AiModelRef → setStageOverride mit LlmRoute (via Adapter)
 * 11. AiModelPicker-Update mit null → clearStageOverride
 * 12. "Override entfernen" Button ruft clearStageOverride
 * 13. "Schliessen" Button schliesst Popover
 * 14. ensureLoaded: loadProviders + defaultsStore.load wenn hasLoadedOnce=false
 * 15. ensureLoaded: kein load wenn providers bereits da und hasLoadedOnce=true
 * 16. i18n-Key: modelLabel
 * 17. i18n-Key: clearOverride (overrideBadge)
 * 18. Adapter-Integration: provider_connection_id → provider_kind (via Store-Lookup)
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import { reactive } from 'vue'
import StepModelOverrideChip from '../StepModelOverrideChip.vue'

// AiModelPicker mocken — wir testen das Glue-Code, nicht den Picker selbst.
const aiPickerStub = {
  name: 'AiModelPicker',
  props: ['modelValue', 'placeholder', 'mode', 'options'],
  emits: ['update:modelValue'],
  template: '<div data-testid="ai-model-picker-stub" @click="$emit(\'update:modelValue\', { provider_connection_id: \'conn-ollama-1\', model_id: \'qwen3\', source: \'explicit\' })">picker</div>',
}

// Legacy-ModelPicker stubben (soll nach 5.4 nicht mehr referenziert werden,
// aber wir stubben ihn, damit die nicht-migrierte Version der Komponente
// nicht beim Render crasht).
const legacyModelPickerStub = {
  name: 'ModelPicker',
  props: ['modelValue', 'placeholder', 'disabled'],
  emits: ['update:modelValue'],
  template: '<select data-testid="legacy-model-picker-stub" disabled></select>',
}

// Reaktive Mock-States — bewusst OHNE vi.hoisted, weil vi.hoisted
// vor dem ESM-Import von `vue` läuft. Stattdessen plain mutable arrays/objects
// mit Getter-Wrapper, der von Pinia-reactive korrekt dereferenziert wird.
const providersArr = reactive<unknown[]>([])
let hasLoadedOnce = false
const stageOverridesMap = reactive<Record<string, unknown>>({})

const llmProvidersMock = {
  get providers() { return providersArr },
  loadProviders: vi.fn().mockResolvedValue(undefined),
}

const llmRoutingDefaultsMock = {
  get hasLoadedOnce() { return hasLoadedOnce },
  get stageOverrides() { return stageOverridesMap },
  effectiveRouteForStage: vi.fn(),
  load: vi.fn().mockResolvedValue(undefined),
  setStageOverride: vi.fn().mockResolvedValue(undefined),
  clearStageOverride: vi.fn().mockResolvedValue(undefined),
}

const adapterMock = {
  toLlmRoute: vi.fn((aiRef: { provider_connection_id: string; model_id: string }) => ({
    stage: null,
    provider_id: 'ollama',
    model: aiRef.model_id,
    temperature: null,
    max_tokens: null,
    reasoning_effort: 'none',
    provider_options: {},
  })),
  toAiModelRef: vi.fn((route: { provider_id?: string | null; model?: string | null }) => ({
    provider_connection_id: route.provider_id ?? 'conn-fallback',
    model_id: route.model ?? '',
    source: 'explicit' as const,
  })),
}

vi.mock('@/store/aiModels', () => ({
  useLlmProvidersStore: () => llmProvidersMock,
  useLlmRoutingDefaultsStore: () => llmRoutingDefaultsMock,
}))

vi.mock('@/composables/useAiModelRefAdapter', () => ({
  useAiModelRefAdapter: () => adapterMock,
}))

// Issue #1023 (Befund B-23): getRunLlmRouting liefert den Run-Snapshot je
// Stage. Der Chip muss ihn bei laufendem/abgeschlossenem Run bevorzugen.
const getRunLlmRoutingMock = vi.fn()
vi.mock('@/api/llmRouting', () => ({
  getRunLlmRouting: (runId: string) => getRunLlmRoutingMock(runId),
}))

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'de',
    fallbackLocale: 'de',
    messages: {
      de: {
        stepModelOverrideChip: {
          label: 'Modell',
          modelPlaceholder: 'Modell wählen …',
          overrideBadge: 'override',
          clearOverride: 'Override entfernen → Default nutzen',
          close: 'Schließen',
          lockedBadge: 'locked',
          sourceRun: 'aus Lauf',
          sourceDefault: 'Standard',
        },
      },
    },
  })
}

async function mountChip(
  props: Record<string, unknown> = {},
  options: { seedProviders?: boolean; seedHasLoadedOnce?: boolean } = {},
) {
  if (options.seedProviders !== false) {
    providersArr.length = 0
    providersArr.push({ id: 'ollama' })
  }
  if (options.seedHasLoadedOnce !== false) {
    hasLoadedOnce = true
  }
  llmProvidersMock.loadProviders.mockClear()
  llmProvidersMock.loadProviders.mockResolvedValue(undefined)
  llmRoutingDefaultsMock.effectiveRouteForStage.mockClear()
  llmRoutingDefaultsMock.setStageOverride.mockClear()
  llmRoutingDefaultsMock.setStageOverride.mockResolvedValue(undefined)
  llmRoutingDefaultsMock.clearStageOverride.mockClear()
  llmRoutingDefaultsMock.clearStageOverride.mockResolvedValue(undefined)
  llmRoutingDefaultsMock.load.mockClear()
  llmRoutingDefaultsMock.load.mockResolvedValue(undefined)
  getRunLlmRoutingMock.mockClear()

  const i18n = makeI18n()
  const pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(StepModelOverrideChip, {
    props: { stageId: 'simulation_rounds', label: 'Modell', ...props },
    global: {
      plugins: [i18n],
      stubs: { AiModelPicker: aiPickerStub, ModelPicker: legacyModelPickerStub },
    },
  })
  await flushPromises()
  return wrapper
}

/** Helper: setzt den stageOverridesMap-State für einen Test. */
function setStageOverrides(entries: Record<string, unknown>): void {
  for (const key of Object.keys(stageOverridesMap)) delete stageOverridesMap[key]
  Object.assign(stageOverridesMap, entries)
}

describe('StepModelOverrideChip (Slice 5.4, AiModelPicker-Migration)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('mountet ohne Crash', async () => {
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: null, provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    const w = await mountChip()
    expect(w.exists()).toBe(true)
    expect(w.find('.step-model-chip').exists()).toBe(true)
  })

  it('zeigt Default-Label aus prop', async () => {
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: null, provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    const w = await mountChip({ label: 'Report-Modell' })
    expect(w.find('.step-model-chip__label').text()).toBe('Report-Modell:')
  })

  it('zeigt model_id aus effektiver Route', async () => {
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: null, provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    const w = await mountChip()
    expect(w.find('.step-model-chip__value').text()).toContain('qwen3')
  })

  it('zeigt "Modell waehlen" wenn Route kein model hat', async () => {
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: null, provider_id: null, model: null, temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    const w = await mountChip()
    expect(w.find('.step-model-chip__value').text()).toContain('Modell wählen')
  })

  it('Klick oeffnet/schliesst Popover', async () => {
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: null, provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    const w = await mountChip()
    expect(w.find('.step-model-chip__popover').exists()).toBe(false)
    await w.find('.step-model-chip').trigger('click')
    expect(w.find('.step-model-chip__popover').exists()).toBe(true)
    await w.find('.step-model-chip').trigger('click')
    expect(w.find('.step-model-chip__popover').exists()).toBe(false)
  })

  it('locked=true: Klick oeffnet Popover nicht', async () => {
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: null, provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    const w = await mountChip({ locked: true })
    await w.find('.step-model-chip').trigger('click')
    expect(w.find('.step-model-chip__popover').exists()).toBe(false)
  })

  it('locked=true: Lock-Icon sichtbar, disabled', async () => {
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: null, provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    const w = await mountChip({ locked: true })
    expect(w.find('.step-model-chip__lock').exists()).toBe(true)
    expect((w.find('.step-model-chip').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('hasOverride: Override-Badge sichtbar', async () => {
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: 'simulation_rounds', provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    setStageOverrides({ simulation_rounds: { provider_id: 'ollama', model: 'qwen3' } })
    const w = await mountChip()
    expect(w.find('.step-model-chip__badge').exists()).toBe(true)
    expect(w.find('.step-model-chip__badge').text()).toContain('override')
  })

  it('kein Override: kein Badge', async () => {
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: null, provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    setStageOverrides({})
    const w = await mountChip()
    expect(w.find('.step-model-chip__badge').exists()).toBe(false)
  })

  it('AiModelPicker-Update mit AiModelRef → setStageOverride mit LlmRoute (via Adapter)', async () => {
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: null, provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    const w = await mountChip()
    await w.find('.step-model-chip').trigger('click')
    const picker = w.findComponent(aiPickerStub)
    expect(picker.exists()).toBe(true)
    await picker.trigger('click') // Stub emittiert hardcoded AiModelRef
    expect(adapterMock.toLlmRoute).toHaveBeenCalledWith({
      provider_connection_id: 'conn-ollama-1',
      model_id: 'qwen3',
      source: 'explicit',
    })
    expect(llmRoutingDefaultsMock.setStageOverride).toHaveBeenCalledWith('simulation_rounds', {
      stage: null,
      provider_id: 'ollama',
      model: 'qwen3',
      temperature: null,
      max_tokens: null,
      reasoning_effort: 'none',
      provider_options: {},
    })
    expect(w.find('.step-model-chip__popover').exists()).toBe(false)
  })

  it('AiModelPicker-Update mit null → clearStageOverride', async () => {
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: null, provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    // Override-spezifisch: Picker zeigt Override aktiv
    setStageOverrides({ simulation_rounds: { provider_id: 'ollama', model: 'qwen3' } })
    const w = await mountChip()
    await w.find('.step-model-chip').trigger('click')
    // Override-Button klicken emittiert null
    await w.find('.step-model-chip__clear').trigger('click')
    expect(llmRoutingDefaultsMock.clearStageOverride).toHaveBeenCalledWith('simulation_rounds')
    expect(w.find('.step-model-chip__popover').exists()).toBe(false)
  })

  it('"Override entfernen" Button ruft clearStageOverride', async () => {
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: 'simulation_rounds', provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    setStageOverrides({ simulation_rounds: { provider_id: 'ollama', model: 'qwen3' } })
    const w = await mountChip()
    await w.find('.step-model-chip').trigger('click')
    expect(w.find('.step-model-chip__clear').exists()).toBe(true)
    await w.find('.step-model-chip__clear').trigger('click')
    expect(llmRoutingDefaultsMock.clearStageOverride).toHaveBeenCalled()
  })

  it('"Schliessen" Button schliesst Popover', async () => {
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: null, provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    const w = await mountChip()
    await w.find('.step-model-chip').trigger('click')
    expect(w.find('.step-model-chip__popover').exists()).toBe(true)
    await w.find('.step-model-chip__close').trigger('click')
    expect(w.find('.step-model-chip__popover').exists()).toBe(false)
  })

  it('ensureLoaded: loadProviders + defaultsStore.load wenn hasLoadedOnce=false', async () => {
    providersArr.length = 0
    hasLoadedOnce = false
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: null, provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    await mountChip({}, { seedProviders: false, seedHasLoadedOnce: false })
    expect(llmProvidersMock.loadProviders).toHaveBeenCalled()
    expect(llmRoutingDefaultsMock.load).toHaveBeenCalled()
  })

  it('ensureLoaded: kein load wenn providers bereits da und hasLoadedOnce=true', async () => {
    providersArr.length = 0
    providersArr.push({ id: 'ollama' })
    hasLoadedOnce = true
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: null, provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    await mountChip({}, { seedProviders: false, seedHasLoadedOnce: false })
    expect(llmProvidersMock.loadProviders).not.toHaveBeenCalled()
    expect(llmRoutingDefaultsMock.load).not.toHaveBeenCalled()
  })

  // Issue #1023 (Befund B-23): der Chip zeigte fuer einen laufenden/
  // abgeschlossenen Run immer den Workspace-/Stage-Default statt des
  // Modells, das der Run fuer diese Stage tatsaechlich verwendet hat.
  it('runId + Run-Snapshot vorhanden: zeigt Snapshot-Modell statt Stage-Default, markiert als "aus Lauf", gesperrt', async () => {
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: null, provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    getRunLlmRoutingMock.mockResolvedValue({
      snapshots: {
        simulation_rounds: {
          stage: 'simulation_rounds',
          provider_id: 'anthropic',
          model: 'claude-sonnet',
          reasoning_effort: 'none',
          routing_version: 1,
        },
      },
    })
    const w = await mountChip({ runId: 'run_a1b2c3d4e5f6' })
    expect(getRunLlmRoutingMock).toHaveBeenCalledWith('run_a1b2c3d4e5f6')
    expect(w.find('.step-model-chip__value').text()).toContain('claude-sonnet')
    expect(w.find('.step-model-chip__value').text()).not.toContain('qwen3')
    expect(w.find('[data-testid="step-model-chip-source"]').text()).toBe('aus Lauf')
    expect((w.find('.step-model-chip').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('runId gesetzt, aber Stage noch ohne Snapshot: faellt auf Stage-Default zurueck, markiert als "Standard"', async () => {
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: null, provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    getRunLlmRoutingMock.mockResolvedValue({ snapshots: {} })
    const w = await mountChip({ runId: 'run_a1b2c3d4e5f6' })
    expect(w.find('.step-model-chip__value').text()).toContain('qwen3')
    expect(w.find('[data-testid="step-model-chip-source"]').text()).toBe('Standard')
    expect((w.find('.step-model-chip').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('ohne runId: zeigt Stage-Default und markiert ihn als "Standard"', async () => {
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: null, provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    const w = await mountChip()
    expect(getRunLlmRoutingMock).not.toHaveBeenCalled()
    expect(w.find('[data-testid="step-model-chip-source"]').text()).toBe('Standard')
  })

  it('i18n: modelLabel placeholder kommt aus i18n-Key', async () => {
    llmRoutingDefaultsMock.effectiveRouteForStage.mockReturnValue({
      stage: null, provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    })
    const w = await mountChip()
    await w.find('.step-model-chip').trigger('click')
    const picker = w.findComponent(aiPickerStub)
    expect(picker.props('placeholder')).toBe('Modell wählen …')
  })
})
