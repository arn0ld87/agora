/**
 * QuotaPlanEditor — Vitest-Spec (Sub-Slice 31, Refs #203).
 *
 * Drei Pflichtcases:
 * (a) Render mit valider PersonaQuotaPlan — kein Validierungs-Fehler sichtbar.
 * (b) Edit emittiert update:entries.
 * (c) Invalid-Plan (leere targets) zeigt Validierungs-Fehler.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { nextTick } from 'vue'

// localStorage stub — muss vor allen Modul-Imports stehen
const localStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach((k) => delete store[k]) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

import QuotaPlanEditor from '../QuotaPlanEditor.vue'

// Minimal i18n with only the keys QuotaPlanEditor uses.
const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    de: {
      step2: {
        quota: {
          toggle: 'Quota aktivieren',
          hintOff: 'Ohne Quote wird pro Entity ein Agent erzeugt.',
          hintOn: 'Segment-Name muss entity_type entsprechen.',
          segmentPlaceholder: 'entity_type',
          addSegment: '+ Segment hinzufügen',
          total: 'Total: {count} Personas',
          invalid: 'Quoten-Plan ungültig.',
        },
      },
    },
    en: {},
  },
})

const globalConfig = {
  plugins: [i18n],
  stubs: {
    Btn: {
      template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
      props: ['disabled', 'variant'],
      emits: ['click'],
    },
  },
}

// ---------------------------------------------------------------------------
// Helper: two valid quota entries (total = 10, targets sum = 10)
// ---------------------------------------------------------------------------
function validEntries() {
  return [
    { id: 'q_1', segment: 'KMU-Chef', count: 6 },
    { id: 'q_2', segment: 'Stadtplaner', count: 4 },
  ]
}

describe('QuotaPlanEditor', () => {
  beforeEach(() => {
    localStorageMock.clear()
  })

  // -------------------------------------------------------------------------
  // (a) Render mit valider PersonaQuotaPlan — kein Fehler sichtbar
  // -------------------------------------------------------------------------
  it('(a) rendert valide Quota-Einträge ohne Validierungsfehler', async () => {
    const wrapper = mount(QuotaPlanEditor, {
      props: {
        enabled: true,
        entries: validEntries(),
        disabled: false,
      },
      global: globalConfig,
    })

    await flushPromises()

    // Segment-Inputs sichtbar
    const segments = wrapper.findAll('input[type="text"]')
    expect(segments).toHaveLength(2)
    expect((segments[0].element as HTMLInputElement).value).toBe('KMU-Chef')
    expect((segments[1].element as HTMLInputElement).value).toBe('Stadtplaner')

    // Count-Inputs vorhanden
    const counts = wrapper.findAll('input[type="number"]')
    expect(counts).toHaveLength(2)

    // Kein Fehler-Element
    const errorEl = wrapper.find('[role="alert"]')
    expect(errorEl.exists()).toBe(false)

    // Total-Anzeige
    expect(wrapper.text()).toContain('10')
  })

  // -------------------------------------------------------------------------
  // (b) Edit emittiert update:entries
  // -------------------------------------------------------------------------
  it('(b) emittiert update:entries wenn ein Segment-Name geändert wird', async () => {
    const wrapper = mount(QuotaPlanEditor, {
      props: {
        enabled: true,
        entries: validEntries(),
        disabled: false,
      },
      global: globalConfig,
    })

    await flushPromises()

    const firstSegmentInput = wrapper.find('input[type="text"]')
    await firstSegmentInput.setValue('Handwerker')
    await nextTick()
    await flushPromises()

    const emitted = wrapper.emitted('update:entries')
    expect(emitted).toBeTruthy()
    expect(emitted!.length).toBeGreaterThanOrEqual(1)

    // Letztes emittiertes Event enthält den neuen Segment-Namen
    const lastEmit = emitted![emitted!.length - 1][0] as Array<{ segment: string; count: number }>
    expect(lastEmit[0].segment).toBe('Handwerker')
  })

  // -------------------------------------------------------------------------
  // (c) Invalid-Plan zeigt Validierungs-Fehler
  // -------------------------------------------------------------------------
  it('(c) zeigt Validierungsfehler bei leerem Segment (targets leer nach Filter)', async () => {
    // One entry with empty segment → buildQuotaPlanFromEntries yields targets:{}, total:0
    const wrapper = mount(QuotaPlanEditor, {
      props: {
        enabled: true,
        entries: [{ id: 'q_1', segment: '', count: 5 }],
        disabled: false,
      },
      global: globalConfig,
    })

    await flushPromises()

    // Error element must be rendered (role="alert")
    const errorEl = wrapper.find('[role="alert"]')
    expect(errorEl.exists()).toBe(true)
    expect(errorEl.text().length).toBeGreaterThan(0)
  })

  // -------------------------------------------------------------------------
  // (d) Disabled — alle Inputs disabled
  // -------------------------------------------------------------------------
  it('(d) disabled=true sperrt alle Eingaben', async () => {
    const wrapper = mount(QuotaPlanEditor, {
      props: {
        enabled: true,
        entries: validEntries(),
        disabled: true,
      },
      global: globalConfig,
    })

    await flushPromises()

    const textInputs = wrapper.findAll('input[type="text"]')
    const numberInputs = wrapper.findAll('input[type="number"]')
    const checkboxes = wrapper.findAll('input[type="checkbox"]')

    for (const el of [...textInputs, ...numberInputs, ...checkboxes]) {
      expect((el.element as HTMLInputElement).disabled).toBe(true)
    }
  })

  // -------------------------------------------------------------------------
  // (e) "+ Segment hinzufügen" emittiert neuen Eintrag
  // -------------------------------------------------------------------------
  it('(e) "+ Segment hinzufügen" emittiert entries mit einem weiteren Eintrag', async () => {
    const wrapper = mount(QuotaPlanEditor, {
      props: {
        enabled: true,
        entries: validEntries(),
        disabled: false,
      },
      global: globalConfig,
    })

    await flushPromises()

    // Click the add-segment button (last button in footer row)
    const buttons = wrapper.findAll('button')
    // Find button whose text contains the addSegment label
    const addBtn = buttons.find((b) => b.text().includes('Segment'))
    expect(addBtn).toBeTruthy()
    await addBtn!.trigger('click')
    await nextTick()

    const emitted = wrapper.emitted('update:entries')
    expect(emitted).toBeTruthy()
    const last = emitted![emitted!.length - 1][0] as unknown[]
    expect(last).toHaveLength(3)
  })

  // -------------------------------------------------------------------------
  // (f) update:enabled emittiert beim Toggle
  // -------------------------------------------------------------------------
  it('(f) emittiert update:enabled beim Checkbox-Klick', async () => {
    const wrapper = mount(QuotaPlanEditor, {
      props: {
        enabled: false,
        entries: [],
        disabled: false,
      },
      global: globalConfig,
    })

    await flushPromises()

    const checkbox = wrapper.find('input[type="checkbox"]')
    await checkbox.setValue(true)
    await nextTick()

    const emitted = wrapper.emitted('update:enabled')
    expect(emitted).toBeTruthy()
    expect(emitted![emitted!.length - 1][0]).toBe(true)
  })
})
