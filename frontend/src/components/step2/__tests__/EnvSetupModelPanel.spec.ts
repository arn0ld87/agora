/**
 * EnvSetupModelPanel — AiModelPicker-Integration (Issue #890, Slice 2).
 *
 * Prueft den kanonischen Modell-Selektions-Pfad (`modelRef` / `update:modelRef`)
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import EnvSetupModelPanel from '../EnvSetupModelPanel.vue'
import type { AiModelRef } from '@/contracts/aiModelRef'

const aiPickerStub = {
  name: 'AiModelPicker',
  props: ['modelValue', 'disabled', 'placeholder', 'mode', 'allowWorkspaceDefault', 'capabilityFilter'],
  emits: ['update:modelValue'],
  template:
    '<div data-testid="ai-model-picker-stub" :data-disabled="disabled">'
    + '<button data-testid="pick-a" @click="$emit(\'update:modelValue\', '
    + "{ provider_connection_id: 'conn-a', model_id: 'model-a', source: 'explicit' })\">pick-a</button>"
    + '<button data-testid="pick-b" @click="$emit(\'update:modelValue\', '
    + "{ provider_connection_id: 'conn-b', model_id: 'model-b', source: 'explicit' })\">pick-b</button>"
    + '<button data-testid="deselect" @click="$emit(\'update:modelValue\', null)">deselect</button>'
    + '</div>',
}

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  fallbackLocale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: { de: {} },
})

function mountPanel(props: Partial<Record<string, unknown>> = {}) {
  return mount(EnvSetupModelPanel, {
    props: {
      language: 'de',
      modelRef: null,
      ...props,
    },
    global: {
      plugins: [i18n],
      stubs: {
        AiModelPicker: aiPickerStub,
        Field: { template: '<div><slot /></div>' },
        Select: { template: '<select><slot /></select>' },
      },
    },
  })
}

describe('EnvSetupModelPanel — AiModelPicker-Integration (#890)', () => {
  it('rendert AiModelPicker', () => {
    const w = mountPanel()
    expect(w.findComponent(aiPickerStub).exists()).toBe(true)
  })

  it('modelRef-Prop initial null -> Picker bekommt null', () => {
    const w = mountPanel({ modelRef: null })
    const picker = w.findComponent(aiPickerStub)
    expect(picker.props('modelValue')).toBeNull()
  })

  it('Picker-Auswahl -> Panel emittiert update:modelRef mit vollstaendigem AiModelRef', async () => {
    const w = mountPanel()
    await w.find('[data-testid="pick-a"]').trigger('click')
    const emitted = w.emitted('update:modelRef')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({
      provider_connection_id: 'conn-a',
      model_id: 'model-a',
      source: 'explicit',
    } satisfies AiModelRef)
  })

  it('Modellwechsel -> neues vollstaendiges Ref wird emittiert', async () => {
    const w = mountPanel()
    await w.find('[data-testid="pick-a"]').trigger('click')
    await w.find('[data-testid="pick-b"]').trigger('click')
    const emitted = w.emitted('update:modelRef')
    expect(emitted).toHaveLength(2)
    expect(emitted![1][0]).toEqual({
      provider_connection_id: 'conn-b',
      model_id: 'model-b',
      source: 'explicit',
    })
  })

  it('Deselektion (Picker emittiert null) -> Panel emittiert update:modelRef mit null', async () => {
    const w = mountPanel({ modelRef: { provider_connection_id: 'conn-a', model_id: 'model-a', source: 'explicit' } })
    await w.find('[data-testid="deselect"]').trigger('click')
    const emitted = w.emitted('update:modelRef')
    expect(emitted).toBeTruthy()
    expect(emitted![emitted!.length - 1][0]).toBeNull()
  })
})
