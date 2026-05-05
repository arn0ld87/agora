/**
 * AddPersonaModal — Vitest-Spec (Sub-Slice 41, Refs #203).
 *
 * Acht Pflichtcases:
 * (1) open=false → Modal nicht im DOM.
 * (2) open=true → Modal im DOM, Titel-Text aus i18n korrekt.
 * (3) Click auf .x-Button emit update:open mit false.
 * (4) Click auf Modal-Backdrop (@click.self) emit update:open mit false.
 * (5) Click auf Submit-Button emit submit-Event.
 * (6) Submit-Button ist disabled bei persona.username.trim() === ''.
 * (7) Submit-Button ist disabled bei saving=true.
 * (8) Input-Change auf username emit update:persona mit komplettem Patch.
 */
import { describe, it, expect } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { nextTick } from 'vue'

import AddPersonaModal from '../AddPersonaModal.vue'
import type { NewPersonaForm } from '../AddPersonaModal.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    de: {
      step2: {
        addPersona: {
          kicker: '№ Neue Persona',
          title: 'Persona manuell anlegen',
          submit: 'Hinzufügen',
          fields: {
            username: 'Username',
            name: 'Anzeigename',
            bio: 'Bio (kurz)',
            profession: 'Beruf / Rolle',
            country: 'Land',
            age: 'Alter',
            gender: 'Gender',
            mbti: 'MBTI',
            topics: 'Interessen (Komma-getrennt)',
            persona: 'Persona-Beschreibung (lang) — Haltung, Rhetorik, Milieu',
          },
          placeholders: {
            username: 'z. B. kritische_buergerin',
            name: 'Anna Meyer',
            bio: 'In einem Satz: wer und wofür.',
            profession: 'Stadtplanerin, Aktivist:in, …',
            country: 'DE',
            topics: 'Überwachung, Datenschutz, Stadtpolitik',
            persona: 'Frei formuliert. Je konkreter, desto charakteristischer reagiert der Agent.',
          },
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
  },
}

function emptyPersona(): NewPersonaForm {
  return {
    username: '',
    name: '',
    bio: '',
    persona: '',
    profession: '',
    country: '',
    age: null,
    gender: 'other',
    mbti: '',
    interested_topics: '',
  }
}

function validPersona(): NewPersonaForm {
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
    interested_topics: 'data, privacy',
  }
}

describe('AddPersonaModal', () => {
  // ---------------------------------------------------------------------------
  // (1) open=false → Modal nicht im DOM
  // ---------------------------------------------------------------------------
  it('(1) rendert Modal nicht wenn open=false', async () => {
    const wrapper = mount(AddPersonaModal, {
      props: {
        open: false,
        persona: emptyPersona(),
        saving: false,
      },
      global: globalConfig,
    })

    await flushPromises()

    expect(wrapper.find('.modal').exists()).toBe(false)
  })

  // ---------------------------------------------------------------------------
  // (2) open=true → Modal im DOM, Titel-Text aus i18n korrekt
  // ---------------------------------------------------------------------------
  it('(2) rendert Modal wenn open=true und zeigt i18n-Titel', async () => {
    const wrapper = mount(AddPersonaModal, {
      props: {
        open: true,
        persona: validPersona(),
        saving: false,
      },
      global: globalConfig,
    })

    await flushPromises()

    expect(wrapper.find('.modal').exists()).toBe(true)
    expect(wrapper.find('h3').text()).toBe('Persona manuell anlegen')
    expect(wrapper.find('.kicker-mono').text()).toBe('№ Neue Persona')
  })

  // ---------------------------------------------------------------------------
  // (3) Click auf .x-Button emit update:open mit false
  // ---------------------------------------------------------------------------
  it('(3) .x-Button emit update:open mit false', async () => {
    const wrapper = mount(AddPersonaModal, {
      props: {
        open: true,
        persona: validPersona(),
        saving: false,
      },
      global: globalConfig,
    })

    await flushPromises()

    await wrapper.find('.x').trigger('click')
    await nextTick()

    const emitted = wrapper.emitted('update:open')
    expect(emitted).toBeTruthy()
    expect(emitted![emitted!.length - 1][0]).toBe(false)
  })

  // ---------------------------------------------------------------------------
  // (4) Click auf Modal-Backdrop emit update:open mit false
  // ---------------------------------------------------------------------------
  it('(4) Backdrop-Click emit update:open mit false', async () => {
    const wrapper = mount(AddPersonaModal, {
      props: {
        open: true,
        persona: validPersona(),
        saving: false,
      },
      global: globalConfig,
    })

    await flushPromises()

    // Trigger the click.self on the .modal backdrop element directly
    await wrapper.find('.modal').trigger('click')
    await nextTick()

    const emitted = wrapper.emitted('update:open')
    expect(emitted).toBeTruthy()
    expect(emitted![emitted!.length - 1][0]).toBe(false)
  })

  // ---------------------------------------------------------------------------
  // (5) Click auf Submit-Button emit submit-Event
  // ---------------------------------------------------------------------------
  it('(5) Submit-Button emit submit', async () => {
    const wrapper = mount(AddPersonaModal, {
      props: {
        open: true,
        persona: validPersona(),
        saving: false,
      },
      global: globalConfig,
    })

    await flushPromises()

    const buttons = wrapper.findAll('button')
    const submitBtn = buttons.find((b) => b.text().includes('Hinzufügen'))
    expect(submitBtn).toBeTruthy()

    await submitBtn!.trigger('click')
    await nextTick()

    expect(wrapper.emitted('submit')).toBeTruthy()
  })

  // ---------------------------------------------------------------------------
  // (6) Submit-Button ist disabled bei username.trim() === ''
  // ---------------------------------------------------------------------------
  it('(6) Submit-Button disabled bei leerem username', async () => {
    const wrapper = mount(AddPersonaModal, {
      props: {
        open: true,
        persona: emptyPersona(),
        saving: false,
      },
      global: globalConfig,
    })

    await flushPromises()

    const buttons = wrapper.findAll('button')
    const submitBtn = buttons.find((b) => b.text().includes('Hinzufügen'))
    expect(submitBtn).toBeTruthy()
    expect((submitBtn!.element as HTMLButtonElement).disabled).toBe(true)
  })

  // ---------------------------------------------------------------------------
  // (7) Submit-Button ist disabled bei saving=true
  // ---------------------------------------------------------------------------
  it('(7) Submit-Button disabled bei saving=true', async () => {
    const wrapper = mount(AddPersonaModal, {
      props: {
        open: true,
        persona: validPersona(),
        saving: true,
      },
      global: globalConfig,
    })

    await flushPromises()

    const buttons = wrapper.findAll('button')
    const submitBtn = buttons.find((b) => b.text().includes('Hinzufügen'))
    expect(submitBtn).toBeTruthy()
    expect((submitBtn!.element as HTMLButtonElement).disabled).toBe(true)
  })

  // ---------------------------------------------------------------------------
  // (8) Input-Change auf username emit update:persona mit komplettem Patch
  // ---------------------------------------------------------------------------
  it('(8) Input auf username emit update:persona mit Patch', async () => {
    const persona = validPersona()
    const wrapper = mount(AddPersonaModal, {
      props: {
        open: true,
        persona,
        saving: false,
      },
      global: globalConfig,
    })

    await flushPromises()

    const usernameInput = wrapper.find('input[type="text"]')
    await usernameInput.setValue('neue_persona')
    await nextTick()
    await flushPromises()

    const emitted = wrapper.emitted('update:persona')
    expect(emitted).toBeTruthy()
    const lastEmit = emitted![emitted!.length - 1][0] as NewPersonaForm
    expect(lastEmit.username).toBe('neue_persona')
    // Alle anderen Felder bleiben erhalten
    expect(lastEmit.name).toBe(persona.name)
    expect(lastEmit.bio).toBe(persona.bio)
  })
})
