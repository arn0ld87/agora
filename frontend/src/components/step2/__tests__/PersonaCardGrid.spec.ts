/**
 * PersonaCardGrid — Vitest-Spec (Sub-Slice 44, Refs #203).
 *
 * 12 Pflichtcases:
 *  (1)  Leeres personas-Array → kein .personas-grid-Element gerendert.
 *  (2)  Personas-Liste → korrekte Anzahl Cards.
 *  (3)  Click auf .persona-body → emit select mit komplettem Persona-Objekt.
 *  (4)  Click auf .persona-del → emit remove mit persona.username.
 *  (5)  Click auf .persona-save → emit save mit komplettem Persona-Objekt.
 *  (6)  savingPersonaKeys.has(profileKey(p)) → .persona-save hat disabled-Attribut.
 *  (7)  getIssuesFor returns 2 issues → Hinweis-Badge mit Text "2 Hinweise".
 *  (8)  getIssuesFor returns 1 issue → Hinweis-Badge mit Text "ein Hinweis".
 *  (9)  getIssuesFor returns 0 issues → kein Hinweis-Badge.
 * (10)  persona.is_manual=true → .persona-tag-Element mit Text "manuell".
 * (11)  persona.bio.length > 90 → Bio mit Ellipsis (Slice + …).
 * (12)  persona.interested_topics → erste 3 Topics gerendert mit " · " als Trenner.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { nextTick } from 'vue'

import PersonaCardGrid from '../PersonaCardGrid.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    de: {
      step2: {
        cardGrid: {
          manual: 'manuell',
          ruleBased: 'Platzhalter',
          delete: 'Persona löschen',
          save: 'Persona speichern',
          hintCount: 'kein Hinweis | ein Hinweis | {count} Hinweise',
        },
      },
    },
    en: {
      step2: {
        cardGrid: {
          manual: 'manual',
          ruleBased: 'Placeholder',
          delete: 'Delete persona',
          save: 'Save persona',
          hintCount: 'no hint | one hint | {count} hints',
        },
      },
    },
  },
})

const globalConfig = {
  plugins: [i18n],
  stubs: {
    Badge: {
      template: '<span class="badge"><slot /></span>',
      // title bleibt bewusst undeklariert — es fällt wie in der echten
      // Badge-Komponente als HTML-Attribut auf das Wurzelelement durch.
      props: ['variant', 'dot'],
    },
  },
}

function makePersona(overrides: Record<string, unknown> = {}) {
  return {
    user_id: 'u1',
    username: 'test_user',
    name: 'Test User',
    bio: 'A short bio.',
    interested_topics: ['topic1', 'topic2', 'topic3'],
    review_status: 'approved',
    is_manual: false,
    ...overrides,
  }
}

function makeDefaultProps(personaOverrides: Record<string, unknown> = {}) {
  return {
    personas: [makePersona(personaOverrides)],
    savingPersonaKeys: new Set<string>(),
    statusVariant: vi.fn().mockReturnValue('success'),
    statusLabel: vi.fn().mockReturnValue('Freigegeben'),
    issueBadgeVariant: vi.fn().mockReturnValue('warning'),
    getIssuesFor: vi.fn().mockReturnValue([]),
    highestSeverityFor: vi.fn().mockReturnValue(''),
    profileKey: vi.fn().mockImplementation((p: { username: string }) => p.username),
  }
}

describe('PersonaCardGrid', () => {
  // ---------------------------------------------------------------------------
  // (1) Leeres personas-Array → kein .personas-grid-Element
  // ---------------------------------------------------------------------------
  it('(1) rendert kein .personas-grid bei leerem personas-Array', async () => {
    const wrapper = mount(PersonaCardGrid, {
      props: {
        ...makeDefaultProps(),
        personas: [],
      },
      global: globalConfig,
    })

    await flushPromises()

    expect(wrapper.find('.personas-grid').exists()).toBe(false)
  })

  // ---------------------------------------------------------------------------
  // (2) Personas-Liste → korrekte Anzahl Cards
  // ---------------------------------------------------------------------------
  it('(2) rendert korrekte Anzahl Cards', async () => {
    const personas = [makePersona({ username: 'u1' }), makePersona({ username: 'u2' }), makePersona({ username: 'u3' })]
    const wrapper = mount(PersonaCardGrid, {
      props: {
        ...makeDefaultProps(),
        personas,
      },
      global: globalConfig,
    })

    await flushPromises()

    expect(wrapper.findAll('.persona--card').length).toBe(3)
  })

  // ---------------------------------------------------------------------------
  // (3) Click auf .persona-body → emit select mit komplettem Persona-Objekt
  // ---------------------------------------------------------------------------
  it('(3) Click auf .persona-body emit select mit komplettem Persona', async () => {
    const persona = makePersona()
    const wrapper = mount(PersonaCardGrid, {
      props: {
        ...makeDefaultProps(),
        personas: [persona],
      },
      global: globalConfig,
    })

    await flushPromises()
    await wrapper.find('.persona-body').trigger('click')
    await nextTick()

    const emitted = wrapper.emitted('select')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual(persona)
  })

  // ---------------------------------------------------------------------------
  // (4) Click auf .persona-del → emit remove mit persona.username
  // ---------------------------------------------------------------------------
  it('(4) Click auf .persona-del emit remove mit username', async () => {
    const persona = makePersona({ username: 'del_user' })
    const wrapper = mount(PersonaCardGrid, {
      props: {
        ...makeDefaultProps(),
        personas: [persona],
      },
      global: globalConfig,
    })

    await flushPromises()
    await wrapper.find('.persona-del').trigger('click')
    await nextTick()

    const emitted = wrapper.emitted('remove')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toBe('del_user')
  })

  // ---------------------------------------------------------------------------
  // (5) Click auf .persona-save → emit save mit komplettem Persona-Objekt
  // ---------------------------------------------------------------------------
  it('(5) Click auf .persona-save emit save mit komplettem Persona', async () => {
    const persona = makePersona()
    const wrapper = mount(PersonaCardGrid, {
      props: {
        ...makeDefaultProps(),
        personas: [persona],
      },
      global: globalConfig,
    })

    await flushPromises()
    await wrapper.find('.persona-save').trigger('click')
    await nextTick()

    const emitted = wrapper.emitted('save')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual(persona)
  })

  // ---------------------------------------------------------------------------
  // (6) savingPersonaKeys.has(profileKey(p)) → .persona-save hat disabled
  // ---------------------------------------------------------------------------
  it('(6) .persona-save ist disabled wenn savingPersonaKeys aktiv', async () => {
    const persona = makePersona({ username: 'saving_user' })
    const wrapper = mount(PersonaCardGrid, {
      props: {
        ...makeDefaultProps(),
        personas: [persona],
        savingPersonaKeys: new Set(['saving_user']),
        profileKey: vi.fn().mockImplementation((p: { username: string }) => p.username),
      },
      global: globalConfig,
    })

    await flushPromises()

    const saveBtn = wrapper.find('.persona-save')
    expect((saveBtn.element as HTMLButtonElement).disabled).toBe(true)
  })

  // ---------------------------------------------------------------------------
  // (7) getIssuesFor returns 2 issues → Badge mit "2 Hinweise"
  // ---------------------------------------------------------------------------
  it('(7) 2 issues → Hinweis-Badge "2 Hinweise"', async () => {
    const persona = makePersona()
    const props = makeDefaultProps()
    props.getIssuesFor = vi.fn().mockReturnValue([
      { code: 'E1', severity: 'error' },
      { code: 'E2', severity: 'warning' },
    ])
    const wrapper = mount(PersonaCardGrid, {
      props: { ...props, personas: [persona] },
      global: globalConfig,
    })

    await flushPromises()

    const badges = wrapper.findAll('.badge')
    const hintBadge = badges.find((b) => b.text().includes('Hinweise'))
    expect(hintBadge).toBeTruthy()
    expect(hintBadge!.text()).toBe('2 Hinweise')
  })

  // ---------------------------------------------------------------------------
  // (8) getIssuesFor returns 1 issue → Badge mit "ein Hinweis"
  // ---------------------------------------------------------------------------
  it('(8) 1 issue → Hinweis-Badge "ein Hinweis"', async () => {
    const persona = makePersona()
    const props = makeDefaultProps()
    props.getIssuesFor = vi.fn().mockReturnValue([{ code: 'E1', severity: 'error' }])
    const wrapper = mount(PersonaCardGrid, {
      props: { ...props, personas: [persona] },
      global: globalConfig,
    })

    await flushPromises()

    const badges = wrapper.findAll('.badge')
    const hintBadge = badges.find((b) => b.text().includes('Hinweis'))
    expect(hintBadge).toBeTruthy()
    expect(hintBadge!.text()).toBe('ein Hinweis')
  })

  // ---------------------------------------------------------------------------
  // (9) getIssuesFor returns 0 issues → kein Hinweis-Badge
  // ---------------------------------------------------------------------------
  it('(9) 0 issues → kein Hinweis-Badge', async () => {
    const persona = makePersona({ review_status: undefined })
    const props = makeDefaultProps()
    props.getIssuesFor = vi.fn().mockReturnValue([])
    const wrapper = mount(PersonaCardGrid, {
      props: { ...props, personas: [persona] },
      global: globalConfig,
    })

    await flushPromises()

    // No hint badge rendered; review_status is undefined so also no status badge
    const badges = wrapper.findAll('.badge')
    const hintBadge = badges.find((b) => b.text().includes('Hinweis'))
    expect(hintBadge).toBeUndefined()
  })

  // ---------------------------------------------------------------------------
  // (10) persona.is_manual=true → .persona-tag mit Text "manuell"
  // ---------------------------------------------------------------------------
  it('(10) is_manual=true → .persona-tag mit Text "manuell"', async () => {
    const persona = makePersona({ is_manual: true })
    const wrapper = mount(PersonaCardGrid, {
      props: {
        ...makeDefaultProps(),
        personas: [persona],
      },
      global: globalConfig,
    })

    await flushPromises()

    const tag = wrapper.find('.persona-tag')
    expect(tag.exists()).toBe(true)
    expect(tag.text()).toBe('manuell')
  })

  // ---------------------------------------------------------------------------
  // (11) bio.length > 90 → Bio mit Ellipsis
  // ---------------------------------------------------------------------------
  it('(11) bio.length > 90 → Bio endet mit "…"', async () => {
    const longBio = 'x'.repeat(95)
    const persona = makePersona({ bio: longBio })
    const wrapper = mount(PersonaCardGrid, {
      props: {
        ...makeDefaultProps(),
        personas: [persona],
      },
      global: globalConfig,
    })

    await flushPromises()

    const bioEl = wrapper.find('.persona-bio')
    expect(bioEl.text()).toContain('…')
    expect(bioEl.text()).toBe('x'.repeat(90) + '…')
  })

  // ---------------------------------------------------------------------------
  // (12) interested_topics → erste 3 Topics mit " · " Trenner
  // ---------------------------------------------------------------------------
  it('(12) interested_topics → erste 3 Topics mit " · " Trenner', async () => {
    const persona = makePersona({ interested_topics: ['Alpha', 'Beta', 'Gamma', 'Delta'] })
    const wrapper = mount(PersonaCardGrid, {
      props: {
        ...makeDefaultProps(),
        personas: [persona],
      },
      global: globalConfig,
    })

    await flushPromises()

    const topicsEl = wrapper.find('.persona-topics')
    expect(topicsEl.exists()).toBe(true)
    expect(topicsEl.text()).toBe('Alpha · Beta · Gamma')
  })

  // ---------------------------------------------------------------------------
  // (13-16) Issue #1029 — Platzhalter-Kennzeichnung
  //
  // Regelbasierte Profile entstehen nach drei gescheiterten LLM-Versuchen
  // und nehmen regulär an der Simulation teil. Ohne Kennzeichnung sind ihre
  // Beiträge im Report nicht von echten Stimmen zu unterscheiden.
  // ---------------------------------------------------------------------------
  function mountWithSource(overrides: Record<string, unknown>) {
    return mount(PersonaCardGrid, {
      props: { ...makeDefaultProps(), personas: [makePersona(overrides)] },
      global: globalConfig,
    })
  }

  it('(13) generation_source=rule_based → Platzhalter-Badge', async () => {
    const wrapper = mountWithSource({ generation_source: 'rule_based' })
    await flushPromises()
    expect(wrapper.text()).toContain('Platzhalter')
  })

  it('(14) generation_source=llm → kein Platzhalter-Badge', async () => {
    const wrapper = mountWithSource({ generation_source: 'llm' })
    await flushPromises()
    expect(wrapper.text()).not.toContain('Platzhalter')
  })

  it('(15) fehlendes generation_source → kein Platzhalter-Badge', async () => {
    // Personas von vor #1029 tragen das Feld nicht.
    const wrapper = mountWithSource({})
    await flushPromises()
    expect(wrapper.text()).not.toContain('Platzhalter')
  })

  it('(16) generation_error landet als title am Badge', async () => {
    const wrapper = mountWithSource({
      generation_source: 'rule_based',
      generation_error: 'LLM-Generierung nach 3 Versuchen fehlgeschlagen',
    })
    await flushPromises()

    const badge = wrapper.findAll('.badge').find((b) => b.text() === 'Platzhalter')
    expect(badge?.attributes('title')).toBe('LLM-Generierung nach 3 Versuchen fehlgeschlagen')
  })
})
