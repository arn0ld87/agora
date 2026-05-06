/**
 * PersonaDetailModal — Vitest-Spec (Sub-Slice 42, Refs #203).
 *
 * 14 Pflichtcases:
 *  (1)  selectedProfile=null → Modal nicht im DOM.
 *  (2)  selectedProfile gesetzt → Modal im DOM, Header-Text aus selectedProfile.name.
 *  (3)  Backdrop-Click emit update:selectedProfile=null UND cancel-editing.
 *  (4)  x-Button-Click emit update:selectedProfile=null UND cancel-editing.
 *  (5)  Read-Modus + Approve-Button-Click → emit approve.
 *  (6)  Read-Modus + Reject-Button-Click → emit reject.
 *  (7)  Read-Modus + Regenerate-Button-Click → emit regenerate.
 *  (8)  Read-Modus + Edit-Button-Click → emit start-editing.
 *  (9)  Edit-Modus + Save-Click → emit save.
 * (10)  Edit-Modus + Cancel-Click → emit cancel-editing.
 * (11)  Regenerate-Hint-Input-Change → emit update:regenerateHint.
 * (12)  Edit-Field-Input (name) → emit update:editingProfile mit Patch.
 * (13)  getIssuesFor returns 2 issues → 2 <li>-Elemente in .review-issues.
 * (14)  reviewActionError gesetzt → .review-error-Element mit Text.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { nextTick } from 'vue'

import PersonaDetailModal from '../PersonaDetailModal.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    de: {
      step2: {
        detailModal: {
          kicker: '№ Persona',
          reviewActive: 'Review aktiv',
          actions: {
            edit: 'Bearbeiten',
            reject: 'Ablehnen',
            approve: 'Freigeben',
            save: 'Speichern',
          },
          fields: {
            age: 'Alter',
            gender: 'Gender',
            mbti: 'MBTI',
            country: 'Land',
            profession: 'Beruf',
            displayName: 'Anzeigename',
            bioShort: 'Bio (kurz)',
            topicsCsv: 'Interessen (Komma-getrennt)',
            personaLong: 'Persona-Beschreibung',
          },
        },
        persona: {
          regenerate: 'Neu generieren',
          regenerateHint: 'Prompt-Hinweis (optional)',
        },
      },
      step5: {
        agent: {
          interests: 'Interessen',
        },
      },
      common: {
        cancel: 'Abbrechen',
        close: 'Schließen',
      },
    },
    en: {},
  },
})

const globalConfig = {
  plugins: [i18n],
  stubs: {
    Btn: {
      template:
        '<button :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
      props: ['disabled', 'variant', 'loading'],
      emits: ['click'],
    },
    Badge: {
      template: '<span class="badge"><slot /></span>',
      props: ['variant', 'dot'],
    },
  },
}

function makeProfile(overrides = {}) {
  return {
    username: 'test_user',
    name: 'Test User',
    bio: 'A test bio.',
    persona: 'A longer persona description.',
    profession: 'Engineer',
    country: 'DE',
    age: 35,
    gender: 'other',
    mbti: 'INTJ',
    interested_topics: ['data', 'privacy'],
    review_status: 'pending',
    ...overrides,
  }
}

function makeEditingProfile(overrides = {}) {
  return {
    name: 'Edit User',
    profession: 'Tester',
    bio: 'Edit bio',
    country: 'AT',
    age: 30,
    gender: 'female',
    mbti: 'ENFP',
    interested_topics: 'testing, vitest',
    persona: 'Edit persona description.',
    ...overrides,
  }
}

function defaultProps(overrides = {}) {
  return {
    selectedProfile: makeProfile(),
    editingProfile: null,
    reviewActionPending: false,
    reviewActionError: '',
    regenerateHint: '',
    reviewEnabled: false,
    statusVariant: vi.fn().mockReturnValue('default'),
    statusLabel: vi.fn().mockReturnValue('Ausstehend'),
    issueBadgeVariant: vi.fn().mockReturnValue('warn'),
    getIssuesFor: vi.fn().mockReturnValue([]),
    highestSeverityFor: vi.fn().mockReturnValue(''),
    ...overrides,
  }
}

describe('PersonaDetailModal', () => {
  // ---------------------------------------------------------------------------
  // (1) selectedProfile=null → Modal nicht im DOM
  // ---------------------------------------------------------------------------
  it('(1) rendert Modal nicht wenn selectedProfile=null', async () => {
    const wrapper = mount(PersonaDetailModal, {
      props: { ...defaultProps(), selectedProfile: null },
      global: globalConfig,
    })
    await flushPromises()
    expect(wrapper.find('.modal').exists()).toBe(false)
  })

  // ---------------------------------------------------------------------------
  // (2) selectedProfile gesetzt → Modal im DOM, Header-Text aus selectedProfile.name
  // ---------------------------------------------------------------------------
  it('(2) rendert Modal wenn selectedProfile gesetzt und zeigt Name', async () => {
    const wrapper = mount(PersonaDetailModal, {
      props: defaultProps(),
      global: globalConfig,
    })
    await flushPromises()
    expect(wrapper.find('.modal').exists()).toBe(true)
    expect(wrapper.find('h3').text()).toBe('Test User')
    expect(wrapper.find('.kicker-mono').text()).toBe('№ Persona')
  })

  // ---------------------------------------------------------------------------
  // (3) Backdrop-Click emit update:selectedProfile=null UND cancel-editing
  // ---------------------------------------------------------------------------
  it('(3) Backdrop-Click emit update:selectedProfile=null und cancel-editing', async () => {
    const wrapper = mount(PersonaDetailModal, {
      props: defaultProps(),
      global: globalConfig,
    })
    await flushPromises()

    await wrapper.find('.modal').trigger('click')
    await nextTick()

    const emittedProfile = wrapper.emitted('update:selectedProfile')
    expect(emittedProfile).toBeTruthy()
    expect(emittedProfile![emittedProfile!.length - 1][0]).toBeNull()

    const emittedCancel = wrapper.emitted('cancel-editing')
    expect(emittedCancel).toBeTruthy()
  })

  // ---------------------------------------------------------------------------
  // (4) x-Button-Click emit update:selectedProfile=null UND cancel-editing
  // ---------------------------------------------------------------------------
  it('(4) x-Button emit update:selectedProfile=null und cancel-editing', async () => {
    const wrapper = mount(PersonaDetailModal, {
      props: defaultProps(),
      global: globalConfig,
    })
    await flushPromises()

    await wrapper.find('.x').trigger('click')
    await nextTick()

    const emittedProfile = wrapper.emitted('update:selectedProfile')
    expect(emittedProfile).toBeTruthy()
    expect(emittedProfile![emittedProfile!.length - 1][0]).toBeNull()

    const emittedCancel = wrapper.emitted('cancel-editing')
    expect(emittedCancel).toBeTruthy()
  })

  // ---------------------------------------------------------------------------
  // (5) Read-Modus + Approve-Button-Click → emit approve
  // ---------------------------------------------------------------------------
  it('(5) Approve-Button emit approve', async () => {
    const wrapper = mount(PersonaDetailModal, {
      props: defaultProps(),
      global: globalConfig,
    })
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const approveBtn = buttons.find((b) => b.text().includes('Freigeben'))
    expect(approveBtn).toBeTruthy()

    await approveBtn!.trigger('click')
    await nextTick()

    expect(wrapper.emitted('approve')).toBeTruthy()
  })

  // ---------------------------------------------------------------------------
  // (6) Read-Modus + Reject-Button-Click → emit reject
  // ---------------------------------------------------------------------------
  it('(6) Reject-Button emit reject', async () => {
    const wrapper = mount(PersonaDetailModal, {
      props: defaultProps(),
      global: globalConfig,
    })
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const rejectBtn = buttons.find((b) => b.text().includes('Ablehnen'))
    expect(rejectBtn).toBeTruthy()

    await rejectBtn!.trigger('click')
    await nextTick()

    expect(wrapper.emitted('reject')).toBeTruthy()
  })

  // ---------------------------------------------------------------------------
  // (7) Read-Modus + Regenerate-Button-Click → emit regenerate
  // ---------------------------------------------------------------------------
  it('(7) Regenerate-Button emit regenerate', async () => {
    const wrapper = mount(PersonaDetailModal, {
      props: defaultProps(),
      global: globalConfig,
    })
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const regenerateBtn = buttons.find((b) => b.text().includes('Neu generieren'))
    expect(regenerateBtn).toBeTruthy()

    await regenerateBtn!.trigger('click')
    await nextTick()

    expect(wrapper.emitted('regenerate')).toBeTruthy()
  })

  // ---------------------------------------------------------------------------
  // (8) Read-Modus + Edit-Button-Click → emit start-editing
  // ---------------------------------------------------------------------------
  it('(8) Edit-Button emit start-editing', async () => {
    const wrapper = mount(PersonaDetailModal, {
      props: defaultProps(),
      global: globalConfig,
    })
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const editBtn = buttons.find((b) => b.text().includes('Bearbeiten'))
    expect(editBtn).toBeTruthy()

    await editBtn!.trigger('click')
    await nextTick()

    expect(wrapper.emitted('start-editing')).toBeTruthy()
  })

  // ---------------------------------------------------------------------------
  // (9) Edit-Modus + Save-Click → emit save
  // ---------------------------------------------------------------------------
  it('(9) Save-Button im Edit-Modus emit save', async () => {
    const wrapper = mount(PersonaDetailModal, {
      props: { ...defaultProps(), editingProfile: makeEditingProfile() },
      global: globalConfig,
    })
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const saveBtn = buttons.find((b) => b.text().includes('Speichern'))
    expect(saveBtn).toBeTruthy()

    await saveBtn!.trigger('click')
    await nextTick()

    expect(wrapper.emitted('save')).toBeTruthy()
  })

  // ---------------------------------------------------------------------------
  // (10) Edit-Modus + Cancel-Click → emit cancel-editing
  // ---------------------------------------------------------------------------
  it('(10) Cancel-Button im Edit-Modus emit cancel-editing', async () => {
    const wrapper = mount(PersonaDetailModal, {
      props: { ...defaultProps(), editingProfile: makeEditingProfile() },
      global: globalConfig,
    })
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const cancelBtn = buttons.find((b) => b.text().includes('Abbrechen'))
    expect(cancelBtn).toBeTruthy()

    await cancelBtn!.trigger('click')
    await nextTick()

    expect(wrapper.emitted('cancel-editing')).toBeTruthy()
  })

  // ---------------------------------------------------------------------------
  // (11) Regenerate-Hint-Input-Change → emit update:regenerateHint
  // ---------------------------------------------------------------------------
  it('(11) Regenerate-Hint-Input emit update:regenerateHint', async () => {
    const wrapper = mount(PersonaDetailModal, {
      props: defaultProps({ regenerateHint: '' }),
      global: globalConfig,
    })
    await flushPromises()

    const hintInput = wrapper.find('.regenerate-hint-input')
    expect(hintInput.exists()).toBe(true)

    await hintInput.setValue('mein Hinweis')
    await nextTick()
    await flushPromises()

    const emitted = wrapper.emitted('update:regenerateHint')
    expect(emitted).toBeTruthy()
    expect(emitted![emitted!.length - 1][0]).toBe('mein Hinweis')
  })

  // ---------------------------------------------------------------------------
  // (12) Edit-Field-Input (name) → emit update:editingProfile mit Patch
  // ---------------------------------------------------------------------------
  it('(12) Edit-Field name-Input emit update:editingProfile mit Patch', async () => {
    const editing = makeEditingProfile()
    const wrapper = mount(PersonaDetailModal, {
      props: { ...defaultProps(), editingProfile: editing },
      global: globalConfig,
    })
    await flushPromises()

    // First text input in edit form is the name field
    const nameInput = wrapper.find('input[type="text"]')
    expect(nameInput.exists()).toBe(true)

    await nameInput.setValue('Neuer Name')
    await nextTick()
    await flushPromises()

    const emitted = wrapper.emitted('update:editingProfile')
    expect(emitted).toBeTruthy()
    const lastEmit = emitted![emitted!.length - 1][0] as typeof editing
    expect(lastEmit.name).toBe('Neuer Name')
    // Alle anderen Felder bleiben erhalten
    expect(lastEmit.profession).toBe(editing.profession)
    expect(lastEmit.bio).toBe(editing.bio)
  })

  // ---------------------------------------------------------------------------
  // (13) getIssuesFor returns 2 issues → 2 <li>-Elemente in .review-issues
  // ---------------------------------------------------------------------------
  it('(13) 2 Issues → 2 li-Elemente in .review-issues', async () => {
    const twoIssues = [
      { code: 'MISSING_BIO', severity: 'high', detail: { missing: ['bio'] } },
      { code: 'MISSING_MBTI', severity: 'medium' },
    ]
    const wrapper = mount(PersonaDetailModal, {
      props: {
        ...defaultProps(),
        getIssuesFor: vi.fn().mockReturnValue(twoIssues),
      },
      global: globalConfig,
    })
    await flushPromises()

    const issueItems = wrapper.findAll('.review-issues li')
    expect(issueItems).toHaveLength(2)
  })

  // ---------------------------------------------------------------------------
  // (14) reviewActionError gesetzt → .review-error-Element mit Text
  // ---------------------------------------------------------------------------
  it('(14) reviewActionError gesetzt → .review-error-Element sichtbar', async () => {
    const wrapper = mount(PersonaDetailModal, {
      props: { ...defaultProps(), reviewActionError: 'Fehler beim Speichern' },
      global: globalConfig,
    })
    await flushPromises()

    const errorEl = wrapper.find('.review-error')
    expect(errorEl.exists()).toBe(true)
    expect(errorEl.text()).toBe('Fehler beim Speichern')
  })
})
