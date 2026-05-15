import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import PersonaAvatar from '../PersonaAvatar.vue'

const i18n = createI18n({ legacy: false, locale: 'de', messages: { de: {} } })

describe('PersonaAvatar', () => {
  it('rendert Initialen aus persona_id', () => {
    const wrapper = mount(PersonaAvatar, {
      props: { personaId: 'alice42', voiceRegister: 'casual' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('AL')
  })

  it('zeigt voice_register-Buchstabe im Badge', () => {
    const wrapper = mount(PersonaAvatar, {
      props: { personaId: 'bob', voiceRegister: 'formal' },
      global: { plugins: [i18n] },
    })
    // .pa-register zeigt ersten Buchstaben des voice_register
    const badge = wrapper.find('.pa-register')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toBe('f')
  })
})
