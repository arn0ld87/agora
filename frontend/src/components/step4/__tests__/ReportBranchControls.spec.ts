/**
 * ReportBranchControls — Migrations-Spec (Issue #834): v3-Profil-Legacy-Picker
 * durch den kanonischen AiModelPicker abgelöst.
 *
 * Kontext: backend/app/services/branching_service.py erlaubt `llm_profile_id`
 * nicht als Branch-Override (nur llm_model, language, max_agents, time_config,
 * enable_twitter, enable_reddit, persona_additions, persona_removals) — das
 * Feld war funktionslos. Migration auf den kanonischen AiModelPicker.
 *
 * Genau EINE Senke im Payload (`llm_model`), aber ZWEI Schreibpfade in der UI
 * (Picker-`watch` und Freitext-`v-model`), die beide auf dasselbe Feld
 * zielen — die zuletzt ausgeführte Bearbeitung gewinnt. Das wird hier bewusst
 * als reales, getestetes Verhalten festgeschrieben (nicht als Wunschverhalten
 * abgeschwächt).
 *
 * Prüft:
 * 1. Initiale Auswahl leer (kein Modell vorbelegt, mode="chat").
 * 2. Auswahl im AiModelPicker → 'create'-Emit enthält llm_model === model_id,
 *    kein llm_profile_id im Form-Objekt.
 * 3. Wechsel des Modells aktualisiert branchForm.llm_model auf den neuen Wert.
 * 4. Deselektion (null) setzt llm_model auf ''.
 * 5. Freitext, danach Picker-Pick → Picker gewinnt (letzte Bearbeitung).
 * 6. Picker-Pick, danach Freitext → Freitext gewinnt (letzte Bearbeitung).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ReportBranchControls from '../ReportBranchControls.vue'

const aiPickerStub = {
  name: 'AiModelPicker',
  props: ['modelValue', 'mode', 'placeholder', 'disabled', 'allowWorkspaceDefault', 'capabilityFilter'],
  emits: ['update:modelValue'],
  template: '<div data-testid="ai-model-picker-stub" />',
}
const buttonStub = {
  name: 'Button',
  emits: ['click'],
  template: '<button @click="$emit(\'click\', $event)"><slot /></button>',
}

// Leerer Katalog: vue-i18n gibt bei fehlendem Key den Key selbst zurueck.
// Die Selektoren unten greifen deshalb auf `aria-label="step4.branch.*"` zu —
// stabil gegen Uebersetzungsaenderungen, im Gegensatz zu Selektoren auf dem
// sichtbaren Text. `missingWarn`/`fallbackWarn` aus, weil das Fehlen der Keys
// hier gewollt ist (Repo-Konvention, vgl. step2/__tests__/QuotaPlanEditor.spec.ts).
const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: { de: {} },
  missingWarn: false,
  fallbackWarn: false,
})

function mountRBC(props: { branchBusy?: boolean } = {}) {
  return mount(ReportBranchControls, {
    props: { branchBusy: false, ...props },
    global: {
      plugins: [i18n],
      stubs: { AiModelPicker: aiPickerStub, Button: buttonStub },
    },
  })
}

describe('ReportBranchControls (Issue #834 — AiModelPicker-Migration)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('rendert AiModelPicker mit modelValue=null und mode="chat" (keine initiale Auswahl)', () => {
    const w = mountRBC()
    const picker = w.findComponent(aiPickerStub)
    expect(picker.exists()).toBe(true)
    expect(picker.props('modelValue')).toBeNull()
    expect(picker.props('mode')).toBe('chat')
  })

  it('Auswahl im AiModelPicker setzt llm_model auf model_id, create-Emit ohne llm_profile_id', async () => {
    const w = mountRBC()
    const picker = w.findComponent(aiPickerStub)
    await picker.vm.$emit('update:modelValue', {
      provider_connection_id: 'conn-openai-1',
      model_id: 'gpt-4o-mini',
      source: 'explicit',
    })
    await w.vm.$nextTick()

    await w.find('button').trigger('click')

    const emitted = w.emitted('create')
    expect(emitted).toBeTruthy()
    const form = emitted![emitted!.length - 1][0] as Record<string, unknown>
    expect(form.llm_model).toBe('gpt-4o-mini')
    expect(form).not.toHaveProperty('llm_profile_id')
  })

  it('Wechsel des Modells aktualisiert branchForm.llm_model auf den neuen Wert', async () => {
    const w = mountRBC()
    const picker = w.findComponent(aiPickerStub)
    await picker.vm.$emit('update:modelValue', {
      provider_connection_id: 'conn-a', model_id: 'model-a', source: 'explicit',
    })
    await w.vm.$nextTick()
    await picker.vm.$emit('update:modelValue', {
      provider_connection_id: 'conn-b', model_id: 'model-b', source: 'explicit',
    })
    await w.vm.$nextTick()

    const input = w.find('input[aria-label="step4.branch.modelPlaceholder"]')
    expect((input.element as HTMLInputElement).value).toBe('model-b')
  })

  it('Deselektion (null) setzt llm_model auf leeren String zurück', async () => {
    const w = mountRBC()
    const picker = w.findComponent(aiPickerStub)
    await picker.vm.$emit('update:modelValue', {
      provider_connection_id: 'conn-a', model_id: 'model-a', source: 'explicit',
    })
    await w.vm.$nextTick()
    await picker.vm.$emit('update:modelValue', null)
    await w.vm.$nextTick()

    const input = w.find('input[aria-label="step4.branch.modelPlaceholder"]')
    expect((input.element as HTMLInputElement).value).toBe('')
  })

  it('Freitext eingeben, danach Picker-Auswahl → create-Emit trägt das Picker-Modell, nicht den Freitext', async () => {
    const w = mountRBC()
    const input = w.find('input[aria-label="step4.branch.modelPlaceholder"]')

    await input.setValue('mein-custom-modell')
    expect((input.element as HTMLInputElement).value).toBe('mein-custom-modell')

    const picker = w.findComponent(aiPickerStub)
    await picker.vm.$emit('update:modelValue', {
      provider_connection_id: 'conn-openai-1',
      model_id: 'gpt-4o-mini',
      source: 'explicit',
    })
    await w.vm.$nextTick()

    // Picker-Pick überschreibt den zuvor getippten Freitext kommentarlos —
    // letzte Bearbeitung gewinnt.
    expect((input.element as HTMLInputElement).value).toBe('gpt-4o-mini')

    await w.find('button').trigger('click')

    const emitted = w.emitted('create')
    expect(emitted).toBeTruthy()
    const form = emitted![emitted!.length - 1][0] as Record<string, unknown>
    expect(form.llm_model).toBe('gpt-4o-mini')
  })

  it('Picker-Auswahl, danach Freitext eingeben → create-Emit trägt den Freitext, nicht das Picker-Modell', async () => {
    const w = mountRBC()
    const picker = w.findComponent(aiPickerStub)
    await picker.vm.$emit('update:modelValue', {
      provider_connection_id: 'conn-openai-1',
      model_id: 'gpt-4o-mini',
      source: 'explicit',
    })
    await w.vm.$nextTick()

    const input = w.find('input[aria-label="step4.branch.modelPlaceholder"]')
    expect((input.element as HTMLInputElement).value).toBe('gpt-4o-mini')

    // Freitext-Eingabe nach dem Pick überschreibt branchForm.llm_model direkt —
    // die Picker-Anzeige (modelRef) aktualisiert sich dabei NICHT mit, Picker
    // und Freitext-Feld laufen bewusst auseinander (siehe Datei-Kommentar).
    await input.setValue('mein-custom-modell')

    await w.find('button').trigger('click')

    const emitted = w.emitted('create')
    expect(emitted).toBeTruthy()
    const form = emitted![emitted!.length - 1][0] as Record<string, unknown>
    expect(form.llm_model).toBe('mein-custom-modell')
  })
})
