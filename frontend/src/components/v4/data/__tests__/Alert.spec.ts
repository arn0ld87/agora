/**
 * Alert — Tests
 * Slice UI-F · 2026-05-15
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Alert from '../Alert.vue'

describe('Alert', () => {
  it('Test 1: Default-Mount nutzt Tone "info"', () => {
    const wrapper = mount(Alert, {
      slots: { default: 'Hinweis-Body' },
    })

    expect(wrapper.find('.al-root--info').exists()).toBe(true)
    expect(wrapper.find('.al-text').text()).toBe('Hinweis-Body')
    expect(wrapper.attributes('role')).toBe('alert')
  })

  it('Test 2: tone=danger trägt Danger-Klasse', () => {
    const wrapper = mount(Alert, {
      props: { tone: 'danger', title: 'Fehler' },
      slots: { default: 'Etwas lief schief.' },
    })

    expect(wrapper.find('.al-root--danger').exists()).toBe(true)
    expect(wrapper.find('.al-title').text()).toBe('Fehler')
  })

  it('Test 3: dismissible rendert Schließen-Button + emittiert dismiss', async () => {
    const wrapper = mount(Alert, {
      props: { dismissible: true },
      slots: { default: 'X' },
    })

    const btn = wrapper.find('.al-dismiss')
    expect(btn.exists()).toBe(true)
    expect(btn.attributes('aria-label')).toBe('Schließen')

    await btn.trigger('click')
    expect(wrapper.emitted('dismiss')).toHaveLength(1)
  })

  it('Test 4: ohne dismissible kein Schließen-Button', () => {
    const wrapper = mount(Alert, { slots: { default: 'X' } })
    expect(wrapper.find('.al-dismiss').exists()).toBe(false)
  })

  it('Test 5: actions-Slot wird gerendert', () => {
    const wrapper = mount(Alert, {
      props: { tone: 'warning' },
      slots: {
        default: 'Bitte erneut versuchen.',
        actions: '<button data-testid="retry">Retry</button>',
      },
    })

    expect(wrapper.find('.al-actions').exists()).toBe(true)
    expect(wrapper.find('[data-testid="retry"]').exists()).toBe(true)
  })

  it('Test 6: ohne default-Slot + ohne title nur Icon, kein leerer Text', () => {
    const wrapper = mount(Alert, { props: { tone: 'success' } })
    expect(wrapper.find('.al-text').exists()).toBe(false)
    expect(wrapper.find('.al-title').exists()).toBe(false)
    expect(wrapper.find('.al-icon').exists()).toBe(true)
  })
})
