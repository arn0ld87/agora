/**
 * PersonaLibraryPanel — Vitest-Spec (Sub-Slice 45, Refs #203).
 *
 * 10 Pflichtcases:
 *  (1)  Leeres templates-Array → kein .persona-library-list, stattdessen .meta-Empty-Text.
 *  (2)  templates-Array mit 2 Einträgen → 2 <article class="persona-template">-Elemente.
 *  (3)  Refresh-Button-Click → emit refresh.
 *  (4)  Use-Button-Click in einer Card → emit use mit komplettem Template-Objekt.
 *  (5)  Remove-Button-Click (×) in einer Card → emit remove mit template.template_id.
 *  (6)  usingIds.has(template.template_id) → Use-Button hat disabled-Attribut.
 *  (7)  loading=true → Refresh-Button hat disabled-Attribut.
 *  (8)  error="Fehler X" → <p class="meta">Fehler X</p> sichtbar.
 *  (9)  Bio > 120 Zeichen → wird mit … getrunkt.
 * (10)  Template ohne username → kein .persona-handle-Element.
 */
import { describe, it, expect } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { nextTick } from 'vue'

import PersonaLibraryPanel from '../PersonaLibraryPanel.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    de: {
      step2: {
        library: {
          title: 'Persona-Bibliothek',
          hint: 'Gespeicherte Personas kannst du in jeder neuen Simulation wiederverwenden.',
          empty: 'Noch keine gespeicherten Personas.',
          refresh: 'Aktualisieren',
          use: 'Verwenden',
        },
      },
    },
    en: {
      step2: {
        library: {
          title: 'Persona Library',
          hint: 'Reuse saved personas in any new simulation.',
          empty: 'No saved personas yet.',
          refresh: 'Refresh',
          use: 'Use',
        },
      },
    },
  },
})

const globalConfig = {
  plugins: [i18n],
}

function makeTemplate(overrides: Record<string, unknown> = {}) {
  return {
    template_id: 'tpl-1',
    username: 'test_user',
    name: 'Test User',
    bio: 'A short bio.',
    persona: undefined as string | undefined,
    ...overrides,
  }
}

function makeDefaultProps(overrides: Record<string, unknown> = {}) {
  return {
    templates: [makeTemplate()],
    loading: false,
    error: '',
    usingIds: new Set<string>(),
    ...overrides,
  }
}

describe('PersonaLibraryPanel', () => {
  // ---------------------------------------------------------------------------
  // (1) Leeres templates-Array → kein .persona-library-list, stattdessen empty-Text
  // ---------------------------------------------------------------------------
  it('(1) rendert kein .persona-library-list bei leerem templates-Array', async () => {
    const wrapper = mount(PersonaLibraryPanel, {
      props: makeDefaultProps({ templates: [] }),
      global: globalConfig,
    })

    await flushPromises()

    expect(wrapper.find('.persona-library-list').exists()).toBe(false)
    expect(wrapper.text()).toContain('Noch keine gespeicherten Personas.')
  })

  // ---------------------------------------------------------------------------
  // (2) templates-Array mit 2 Einträgen → 2 <article class="persona-template">
  // ---------------------------------------------------------------------------
  it('(2) rendert 2 <article class="persona-template"> bei 2 Templates', async () => {
    const templates = [
      makeTemplate({ template_id: 'tpl-1', username: 'u1' }),
      makeTemplate({ template_id: 'tpl-2', username: 'u2' }),
    ]
    const wrapper = mount(PersonaLibraryPanel, {
      props: makeDefaultProps({ templates }),
      global: globalConfig,
    })

    await flushPromises()

    expect(wrapper.findAll('article.persona-template').length).toBe(2)
  })

  // ---------------------------------------------------------------------------
  // (3) Refresh-Button-Click → emit refresh
  // ---------------------------------------------------------------------------
  it('(3) Klick auf Refresh-Button emittet refresh', async () => {
    const wrapper = mount(PersonaLibraryPanel, {
      props: makeDefaultProps(),
      global: globalConfig,
    })

    await flushPromises()
    await wrapper.find('button.persona-more-btn').trigger('click')
    await nextTick()

    expect(wrapper.emitted('refresh')).toBeTruthy()
  })

  // ---------------------------------------------------------------------------
  // (4) Use-Button-Click → emit use mit komplettem Template-Objekt
  // ---------------------------------------------------------------------------
  it('(4) Klick auf Use-Button emittet use mit Template-Objekt', async () => {
    const template = makeTemplate({ template_id: 'tpl-use', name: 'Use Me' })
    const wrapper = mount(PersonaLibraryPanel, {
      props: makeDefaultProps({ templates: [template] }),
      global: globalConfig,
    })

    await flushPromises()
    const article = wrapper.find('article.persona-template')
    const useBtn = article.find('.persona-template-actions button:first-child')
    await useBtn.trigger('click')
    await nextTick()

    const emitted = wrapper.emitted('use')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual(template)
  })

  // ---------------------------------------------------------------------------
  // (5) Remove-Button-Click (×) → emit remove mit template.template_id
  // ---------------------------------------------------------------------------
  it('(5) Klick auf Remove-Button (×) emittet remove mit template_id', async () => {
    const template = makeTemplate({ template_id: 'tpl-remove' })
    const wrapper = mount(PersonaLibraryPanel, {
      props: makeDefaultProps({ templates: [template] }),
      global: globalConfig,
    })

    await flushPromises()
    const article = wrapper.find('article.persona-template')
    const removeBtn = article.find('.persona-template-actions button:last-child')
    await removeBtn.trigger('click')
    await nextTick()

    const emitted = wrapper.emitted('remove')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toBe('tpl-remove')
  })

  // ---------------------------------------------------------------------------
  // (6) usingIds.has(template_id) → Use-Button hat disabled-Attribut
  // ---------------------------------------------------------------------------
  it('(6) Use-Button ist disabled wenn template_id in usingIds', async () => {
    const template = makeTemplate({ template_id: 'tpl-using' })
    const wrapper = mount(PersonaLibraryPanel, {
      props: makeDefaultProps({
        templates: [template],
        usingIds: new Set(['tpl-using']),
      }),
      global: globalConfig,
    })

    await flushPromises()

    const article = wrapper.find('article.persona-template')
    const useBtn = article.find('.persona-template-actions button:first-child')
    expect((useBtn.element as HTMLButtonElement).disabled).toBe(true)
  })

  // ---------------------------------------------------------------------------
  // (7) loading=true → Refresh-Button hat disabled-Attribut
  // ---------------------------------------------------------------------------
  it('(7) Refresh-Button ist disabled wenn loading=true', async () => {
    const wrapper = mount(PersonaLibraryPanel, {
      props: makeDefaultProps({ loading: true }),
      global: globalConfig,
    })

    await flushPromises()

    const refreshBtn = wrapper.find('button.persona-more-btn')
    expect((refreshBtn.element as HTMLButtonElement).disabled).toBe(true)
  })

  // ---------------------------------------------------------------------------
  // (8) error="Fehler X" → <p class="meta">Fehler X</p> sichtbar
  // ---------------------------------------------------------------------------
  it('(8) error prop rendert Fehlertext in <p class="meta">', async () => {
    const wrapper = mount(PersonaLibraryPanel, {
      props: makeDefaultProps({ error: 'Fehler X' }),
      global: globalConfig,
    })

    await flushPromises()

    const allMetaParas = wrapper.findAll('p.meta')
    const errorPara = allMetaParas.find((p) => p.text() === 'Fehler X')
    expect(errorPara).toBeTruthy()
    expect(errorPara!.text()).toBe('Fehler X')
  })

  // ---------------------------------------------------------------------------
  // (9) Bio > 120 Zeichen → wird mit … getrunkt
  // ---------------------------------------------------------------------------
  it('(9) Bio > 120 Zeichen endet mit "…"', async () => {
    const longBio = 'x'.repeat(125)
    const template = makeTemplate({ bio: longBio })
    const wrapper = mount(PersonaLibraryPanel, {
      props: makeDefaultProps({ templates: [template] }),
      global: globalConfig,
    })

    await flushPromises()

    const article = wrapper.find('article.persona-template')
    const bioP = article.find('p')
    expect(bioP.text()).toContain('…')
    expect(bioP.text()).toBe('x'.repeat(120) + '…')
  })

  // ---------------------------------------------------------------------------
  // (10) Template ohne username → kein .persona-handle-Element
  // ---------------------------------------------------------------------------
  it('(10) Template ohne username rendert kein .persona-handle', async () => {
    const template = makeTemplate({ username: undefined, name: 'Anonym' })
    const wrapper = mount(PersonaLibraryPanel, {
      props: makeDefaultProps({ templates: [template] }),
      global: globalConfig,
    })

    await flushPromises()

    expect(wrapper.find('.persona-handle').exists()).toBe(false)
  })
})
