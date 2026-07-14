/**
 * ReportModelControls — minimaler Migrations-Spec fuer Slice 7.6b.
 *
 * Drei essenzielle Pruefungen:
 *  - Picker-Anbindung: AiModelPicker gerendert, ModelPicker (v4 legacy) NICHT
 *  - v-model: AiModelRef wird durchgereicht
 *  - null-Pfad: emit('update:modelValue', null) funktioniert
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ReportModelControls from '../ReportModelControls.vue'
import type { AiModelRef } from '@/contracts/aiModelRef'

const aiPickerStub = {
  name: 'AiModelPicker',
  props: ['modelValue', 'placeholder', 'mode', 'allowWorkspaceDefault', 'capabilityFilter'],
  emits: ['update:modelValue'],
  template:
    '<div data-testid="ai-model-picker-stub" '
    + '@click="$emit(\'update:modelValue\', { provider_connection_id: \'conn-openai-1\', model_id: \'gpt-4o-mini\', source: \'explicit\' })">picker</div>',
}
const legacyModelPickerStub = {
  name: 'ModelPicker',
  props: ['modelValue', 'placeholder', 'disabled'],
  emits: ['update:modelValue'],
  template: '<select data-testid="legacy-model-picker-stub" disabled></select>',
}
const buttonStub = { name: 'Button', template: '<button><slot /></button>' }

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  fallbackLocale: 'de',
  messages: { de: { step4: { model: { reportLabel: 'Report-Modell', placeholder: 'waehlen', regenerate: 'Neu' } } } },
})

function mountRMC(modelValue: AiModelRef | null = null) {
  return mount(ReportModelControls, {
    props: { modelValue, isRegenerating: false },
    global: {
      plugins: [i18n],
      stubs: { AiModelPicker: aiPickerStub, ModelPicker: legacyModelPickerStub, Button: buttonStub },
    },
  })
}

describe('ReportModelControls (Slice 7.6b, minimal)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('rendert AiModelPicker, nicht ModelPicker (v4 legacy)', async () => {
    const w = mountRMC()
    await flushPromises()
    expect(w.findComponent(aiPickerStub).exists()).toBe(true)
    expect(w.findComponent(legacyModelPickerStub).exists()).toBe(false)
  })

  it('reicht modelValue als AiModelRef an AiModelPicker durch', async () => {
    const aiRef = { provider_connection_id: 'conn-ollama-1', model_id: 'qwen3', source: 'workspace-default' as const }
    const w = mountRMC(aiRef)
    await flushPromises()
    const picker = w.findComponent(aiPickerStub)
    expect(picker.props('modelValue')).toEqual(aiRef)
  })

  it('emit("update:modelValue", null) wird durchgereicht (null-Pfad)', async () => {
    const w = mountRMC({ provider_connection_id: 'c', model_id: 'm', source: 'explicit' as const })
    await flushPromises()
    const picker = w.findComponent(aiPickerStub)
    picker.vm.$emit('update:modelValue', null)
    await flushPromises()
    const emitted = w.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    expect(emitted![emitted!.length - 1]).toEqual([null])
  })
})