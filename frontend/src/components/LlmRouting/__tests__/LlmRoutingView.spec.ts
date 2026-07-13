/**
 * LlmRoutingView (v3) — Spec-Tests fuer Slice 5.4 Migration auf AiModelPicker.
 *
 * Die v3-Komponente rendert Global-Default + Stage-Overrides via ModelPicker
 * (alt) und macht die persistierten Routen via updateRunLlmRouting /
 * patchStageLlmRouting sichtbar. Migration-Fokus:
 *  - ModelPicker (alt) -> AiModelPicker (SSoT) an 2 Stellen
 *  - StageLLMRoute bleibt der v3-Backend-Vertrag; AiModelPicker konvertiert
 *    via useAiModelRefAdapter.toStageLlmRoute fuer Patches.
 *  - Reasoning-Effort-Select bleibt unveraendert.
 *
 * Coverage:
 *  1. mountet ohne Crash
 *  2. onMount: load() ruft getRunLlmRouting + loadProviders
 *  3. AiModelPicker in Global-Default-Section
 *  4. AiModelPicker in Stage-Overrides-Section (pro Stage)
 *  5. onGlobalDefaultPicked: AiModelRef -> adapter.toStageLlmRoute ->
 *     routing.global_default.provider_id + model
 *  6. onGlobalDefaultPicked mit null: keine Aenderung
 *  7. saveGlobal: ruft updateRunLlmRouting mit dem aktualisierten routing
 *  8. onStageOverridePicked: AiModelRef -> routing.stage_overrides[stageId]
 *  9. saveStage: ruft patchStageLlmRouting
 * 10. isStageLocked: true wenn snapshot existiert (Apply-Button disabled)
 * 11. Reasoning-Effort-Select bleibt erhalten
 * 12. Active-Snapshots: zeigt Snapshots
 * 13. Call-Events: zeigt LlmInvocationEvents
 * 14. i18n-Key: llm.routing.global_default
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref, reactive } from 'vue'
import LlmRoutingView from '../LlmRoutingView.vue'

// AiModelPicker mocken
const aiPickerStub = {
  name: 'AiModelPicker',
  props: ['modelValue', 'placeholder', 'mode', 'options', 'disabled'],
  emits: ['update:modelValue'],
  template: '<div :data-testid="\'ai-picker-\' + (disabled ? \'disabled\' : \'enabled\')" @click="$emit(\'update:modelValue\', { provider_connection_id: \'conn-openai-1\', model_id: \'gpt-4o-mini\', source: \'explicit\' })">picker</div>',
}

// ModelPicker stubben
const legacyModelPickerStub = {
  name: 'ModelPicker',
  props: ['modelValue', 'placeholder', 'disabled'],
  emits: ['update:modelValue'],
  template: '<select data-testid="legacy-model-picker" disabled></select>',
}

const {
  getRunLlmRoutingMock,
  updateRunLlmRoutingMock,
  patchStageLlmRoutingMock,
  loadProvidersMock,
  providersArr,
  adapterMock,
} = vi.hoisted(() => ({
  getRunLlmRoutingMock: vi.fn(),
  updateRunLlmRoutingMock: vi.fn(),
  patchStageLlmRoutingMock: vi.fn(),
  loadProvidersMock: vi.fn(),
  providersArr: [{ id: 'ollama' }],
  adapterMock: {
    toStageLlmRoute: vi.fn((aiRef: { provider_connection_id: string; model_id: string }) => ({
      stage: null,
      provider_id: 'openai',
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
  },
}))

vi.mock('../../../api/llmRouting', () => ({
  getRunLlmRouting: getRunLlmRoutingMock,
  updateRunLlmRouting: updateRunLlmRoutingMock,
  patchStageLlmRouting: patchStageLlmRoutingMock,
}))

vi.mock('@/store/llmProviders', () => ({
  useLlmProvidersStore: () => ({
    providers: providersArr,
    loadProviders: loadProvidersMock,
  }),
}))

vi.mock('@/composables/useAiModelRefAdapter', () => ({
  useAiModelRefAdapter: () => adapterMock,
}))

const defaultRouting = {
  global_default: {
    stage: null, provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null,
    reasoning_effort: 'none', provider_options: {},
  },
  stage_overrides: {},
  routing_version: 1,
}

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'de',
    fallbackLocale: 'de',
    messages: {
      de: {
        common: { loading: 'Lade…', save: 'Speichern', apply: 'Anwenden' },
        llm: {
          model: 'Modell',
          provider: 'Provider',
          reasoning_effort: 'Reasoning',
          routing: {
            global_default: 'Global-Default',
            model_placeholder: 'Modell waehlen …',
            stage_overrides: 'Stage-Overrides',
            locked: 'Locked',
            active_snapshots: 'Aktive Snapshots',
            call_events: 'Call-Events',
            no_snapshots_yet: 'Keine Snapshots',
            no_call_events_yet: 'Keine Events',
            success: 'OK',
            failed: 'FAIL',
            latency: 'Latenz',
            error_type: 'Fehlertyp',
          },
          stages: {
            document_ingest: 'Ingest',
            ontology_generation: 'Ontologie',
            graph_build: 'Graph-Build',
            persona_generation: 'Persona-Gen',
            simulation_rounds: 'Simulation',
            report_generation: 'Report',
            evaluation: 'Evaluation',
          },
        },
      },
    },
  })
}

async function mountLlmRouting() {
  loadProvidersMock.mockClear()
  getRunLlmRoutingMock.mockClear()
  getRunLlmRoutingMock.mockResolvedValue({
    runtime_config: defaultRouting,
    snapshots: {},
    invocation_events: [],
  })
  updateRunLlmRoutingMock.mockClear()
  updateRunLlmRoutingMock.mockImplementation(async (_runId: string, routing: unknown) => routing)
  patchStageLlmRoutingMock.mockClear()
  patchStageLlmRoutingMock.mockImplementation(async (_runId: string, _stageId: string, route: unknown) => ({
    global_default: defaultRouting.global_default,
    stage_overrides: { [_stageId]: route },
    routing_version: 2,
  }))
  adapterMock.toStageLlmRoute.mockClear()
  adapterMock.toAiModelRef.mockClear()

  const i18n = makeI18n()
  const wrapper = mount(LlmRoutingView, {
    props: { runId: 'run-test-1' },
    global: {
      plugins: [i18n],
      stubs: {
        AiModelPicker: aiPickerStub,
        ModelPicker: legacyModelPickerStub,
      },
    },
  })
  await flushPromises()
  return wrapper
}

describe('LlmRoutingView v3 (Slice 5.4, AiModelPicker-Migration)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('mountet ohne Crash', async () => {
    const w = await mountLlmRouting()
    expect(w.exists()).toBe(true)
  })

  it('onMount: load() ruft getRunLlmRouting + loadProviders', async () => {
    await mountLlmRouting()
    expect(getRunLlmRoutingMock).toHaveBeenCalledWith('run-test-1')
    expect(loadProvidersMock).toHaveBeenCalled()
  })

  it('AiModelPicker in Global-Default-Section', async () => {
    const w = await mountLlmRouting()
    const pickers = w.findAllComponents(aiPickerStub)
    expect(pickers.length).toBeGreaterThan(0)
  })

  it('AiModelPicker in Stage-Overrides-Section (pro Stage, 7 Stages)', async () => {
    const w = await mountLlmRouting()
    const pickers = w.findAllComponents(aiPickerStub)
    // 1 Global + 7 Stages = 8 Picker insgesamt
    expect(pickers.length).toBe(8)
  })

  it('onGlobalDefaultPicked: AiModelRef -> adapter.toStageLlmRoute -> routing.global_default', async () => {
    const w = await mountLlmRouting()
    const globalPicker = w.findAllComponents(aiPickerStub)[0]
    expect(globalPicker.exists()).toBe(true)
    ;(globalPicker.vm as unknown as { $emit: (e: string, v: unknown) => void }).$emit('update:modelValue', {
      provider_connection_id: 'conn-openai-1',
      model_id: 'gpt-4o-mini',
      source: 'explicit',
    })
    expect(adapterMock.toStageLlmRoute).toHaveBeenCalledWith({
      provider_connection_id: 'conn-openai-1',
      model_id: 'gpt-4o-mini',
      source: 'explicit',
    })
    // routing.value.global_default.provider_id und model wurden gesetzt
    // (defineExpose unwrappt Refs automatisch, exposed.routing ist der Wert)
    const exposed = w.vm as unknown as {
      routing: { global_default: { provider_id: string; model: string } } | null
    }
    expect(exposed.routing?.global_default.provider_id).toBe('openai')
    expect(exposed.routing?.global_default.model).toBe('gpt-4o-mini')
  })

  it('onGlobalDefaultPicked mit null: keine Aenderung', async () => {
    const w = await mountLlmRouting()
    // Snapshot des routing-Werts VOR dem null-Emit
    const exposed = w.vm as unknown as {
      routing: { global_default: { provider_id: string; model: string } } | null
    }
    const before = JSON.stringify(exposed.routing?.global_default)
    const globalPicker = w.findAllComponents(aiPickerStub)[0]
    ;(globalPicker.vm as unknown as { $emit: (e: string, v: unknown) => void }).$emit('update:modelValue', null)
    const after = JSON.stringify(exposed.routing?.global_default)
    expect(after).toBe(before)
  })

  it('saveGlobal: ruft updateRunLlmRouting mit aktualisiertem routing', async () => {
    const w = await mountLlmRouting()
    const exposed = w.vm as unknown as { saveGlobal: () => Promise<void>; routing: unknown }
    await exposed.saveGlobal()
    expect(updateRunLlmRoutingMock).toHaveBeenCalledWith('run-test-1', exposed.routing)
  })

  it('onStageOverridePicked: AiModelRef -> routing.stage_overrides[stageId]', async () => {
    const w = await mountLlmRouting()
    // Stage-Picker = Index 1 (Index 0 = Global)
    const stagePicker = w.findAllComponents(aiPickerStub)[1]
    expect(stagePicker.exists()).toBe(true)
    ;(stagePicker.vm as unknown as { $emit: (e: string, v: unknown) => void }).$emit('update:modelValue', {
      provider_connection_id: 'conn-openai-1',
      model_id: 'gpt-4o-mini',
      source: 'explicit',
    })
    const exposed = w.vm as unknown as {
      routing: { stage_overrides: Record<string, { provider_id: string; model: string }> } | null
    }
    expect(exposed.routing?.stage_overrides['document_ingest']?.provider_id).toBe('openai')
    expect(exposed.routing?.stage_overrides['document_ingest']?.model).toBe('gpt-4o-mini')
  })

  it('saveStage: ruft patchStageLlmRouting', async () => {
    const w = await mountLlmRouting()
    const exposed = w.vm as unknown as {
      saveStage: (stageId: string, route: unknown) => Promise<void>
    }
    const route = { stage: null, provider_id: 'openai', model: 'gpt-4o-mini', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {} }
    await exposed.saveStage('document_ingest', route)
    expect(patchStageLlmRoutingMock).toHaveBeenCalledWith('run-test-1', 'document_ingest', route)
  })

  it('isStageLocked: true wenn snapshot existiert (Apply-Button disabled)', async () => {
    getRunLlmRoutingMock.mockResolvedValueOnce({
      runtime_config: defaultRouting,
      snapshots: { document_ingest: { routing_version: 1, model: 'qwen3', provider_id: 'ollama', started_at: '2026-07-13T00:00:00Z' } },
      invocation_events: [],
    })
    const w = await mountLlmRouting()
    const exposed = w.vm as unknown as {
      isStageLocked: (stageId: string) => boolean
    }
    expect(exposed.isStageLocked('document_ingest')).toBe(true)
    expect(exposed.isStageLocked('ontology_generation')).toBe(false)
  })

  it('Reasoning-Effort-Select bleibt erhalten', async () => {
    const w = await mountLlmRouting()
    // Reasoning-Effort-Select ist im Global-Default-Bereich
    const selects = w.findAll('select')
    // Profile-Select ist im HeroNewRun (hier nicht), Reasoning-Select + stage-locked-Indikatoren
    expect(selects.length).toBeGreaterThan(0)
  })

  it('Active-Snapshots: zeigt Snapshots', async () => {
    getRunLlmRoutingMock.mockResolvedValueOnce({
      runtime_config: defaultRouting,
      snapshots: { document_ingest: { routing_version: 1, model: 'qwen3', provider_id: 'ollama', started_at: '2026-07-13T00:00:00Z' } },
      invocation_events: [],
    })
    const w = await mountLlmRouting()
    expect(w.text()).toContain('qwen3')
  })

  it('Call-Events: zeigt LlmInvocationEvents', async () => {
    getRunLlmRoutingMock.mockResolvedValueOnce({
      runtime_config: defaultRouting,
      snapshots: {},
      invocation_events: [
        { run_id: 'run-test-1', stage: 'document_ingest', provider_id: 'ollama', model: 'qwen3', routing_version: 1, timestamp: Date.now() / 1000, latency_ms: 250, success: true },
      ],
    })
    const w = await mountLlmRouting()
    expect(w.text()).toContain('250')
  })

  it('i18n-Key: llm.routing.global_default rendert "Global-Default"', async () => {
    const w = await mountLlmRouting()
    expect(w.text()).toContain('Global-Default')
  })
})
