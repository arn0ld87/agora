import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import ComingSoonCard from '../ComingSoonCard.vue'

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div/>' } }],
  })
}

describe('ComingSoonCard', () => {
  it('rendert Titel und Beschreibung', () => {
    const w = mount(ComingSoonCard, {
      props: {
        title: 'Coming soon',
        description: 'Folgt im naechsten Epic.',
      },
      global: { plugins: [makeRouter()] },
    })
    expect(w.text()).toContain('Coming soon')
    expect(w.text()).toContain('Folgt im naechsten Epic.')
  })

  it('zeigt keinen Fallback-Link wenn fallbackLabel/-To leer', () => {
    const w = mount(ComingSoonCard, {
      props: { title: 'T', description: 'D' },
      global: { plugins: [makeRouter()] },
    })
    expect(w.find('.v4-coming-soon__link').exists()).toBe(false)
  })

  it('zeigt Fallback-Link wenn beide Props gesetzt sind', () => {
    const w = mount(ComingSoonCard, {
      props: {
        title: 'T',
        description: 'D',
        fallbackLabel: 'Zum klassischen Tab',
        fallbackTo: '/settings',
      },
      global: { plugins: [makeRouter()] },
    })
    const link = w.find('.v4-coming-soon__link')
    expect(link.exists()).toBe(true)
    expect(link.text()).toBe('Zum klassischen Tab')
  })
})
