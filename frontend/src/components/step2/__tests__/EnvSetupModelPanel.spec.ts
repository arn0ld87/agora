/**
 * EnvSetupModelPanel — AiModelPicker-Integration (Issue #890, Slice 2).
 *
 * Prueft den kanonischen Modell-Selektions-Pfad (`modelRef` / `update:modelRef`)
 * getrennt vom Legacy-Runtime-Provider-Pfad (`modelOption` / `update:modelOption`).
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
      modelOption: 'default',
      modelOptions: [],
      customModel: '',
      language: 'de',
      runtimeProviderOptions: [],
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

  it('modelPickerDisabled=true -> Picker ist disabled', () => {
    const w = mountPanel({ modelPickerDisabled: true })
    const picker = w.findComponent(aiPickerStub)
    expect(picker.props('disabled')).toBe(true)
  })

  it('keine Legacy-Modell-Events auf dem Kanon-Pfad: Picker-Auswahl loest KEIN update:modelOption/update:customModel aus', async () => {
    const w = mountPanel()
    await w.find('[data-testid="pick-a"]').trigger('click')
    expect(w.emitted('update:modelOption')).toBeUndefined()
    expect(w.emitted('update:customModel')).toBeUndefined()
  })

  // Lücke 2 (Lead-Review, Spec-Findings): runtimeProviderBlockDisabled war
  // ungetestet. Der Runtime-Provider-Block muss erreichbar sein, solange
  // keine kanonische Auswahl aktiv ist (modelRef === null), und ausgeblendet
  // werden, sobald sie aktiv ist (modelRef !== null) — Backend-400-Guard.
  describe('runtimeProviderBlockDisabled — gegenseitiger Ausschluss (Issue #890)', () => {
    it('modelRef=null -> Runtime-Provider-Toggle ist NICHT disabled und oeffnet den Runtime-Block', async () => {
      const w = mountPanel({ modelRef: null })
      const toggle = w.find('.runtime-toggle')
      expect(toggle.attributes('disabled')).toBeUndefined()

      await toggle.trigger('click')

      expect(w.find('.runtime-panel').exists()).toBe(true)
    })

    it('modelRef gesetzt -> Runtime-Provider-Toggle ist disabled und der Runtime-Block bleibt ausgeblendet', async () => {
      const w = mountPanel({
        modelRef: { provider_connection_id: 'conn-a', model_id: 'model-a', source: 'explicit' },
      })
      const toggle = w.find('.runtime-toggle')
      expect(toggle.attributes('disabled')).toBeDefined()

      await toggle.trigger('click')

      expect(w.find('.runtime-panel').exists()).toBe(false)
    })
  })
})
