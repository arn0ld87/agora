import { describe, it, expect, beforeAll } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import FeedColumn from '../FeedColumn.vue'

// IntersectionObserver ist in jsdom nicht vorhanden — globaler Stub
beforeAll(() => {
  if (!globalThis.IntersectionObserver) {
    globalThis.IntersectionObserver = class MockIntersectionObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof IntersectionObserver
  }
})

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: { de: { common: { scrollToBottom: 'Zum aktuellen Beitrag springen' } } },
})

describe('FeedColumn', () => {
  it('rendert channel-title im Header', () => {
    const wrapper = mount(FeedColumn, {
      props: { title: 'Reddit', channel: 'reddit' },
      slots: { default: '<div class="test-slot">Inhalt</div>' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Reddit')
  })

  it('rendert Slot-Inhalt', () => {
    const wrapper = mount(FeedColumn, {
      props: { title: 'Twitter', channel: 'twitter' },
      slots: { default: '<p class="test-post">Post 1</p>' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.test-post').exists()).toBe(true)
  })

  // Issue #838: role="feed" verlangt Kinder mit role="article". Eine leere
  // Spalte hat keine, axe-core meldet das als aria-required-children
  // (critical). Die Rolle haengt deshalb an hasItems — der bisherige Test
  // pinnte den ungueltigen Zustand der leeren Spalte.
  it('hat role=feed auf Root-Element, sobald Beitraege vorhanden sind', () => {
    const wrapper = mount(FeedColumn, {
      props: { title: 'Reddit', channel: 'reddit', hasItems: true },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('[role="feed"]').exists()).toBe(true)
  })

  it('faellt ohne Beitraege auf role=region zurueck statt auf einen leeren Feed', () => {
    const wrapper = mount(FeedColumn, {
      props: { title: 'Reddit', channel: 'reddit' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('[role="feed"]').exists()).toBe(false)
    const region = wrapper.find('[role="region"]')
    expect(region.exists()).toBe(true)
    // Die Spalte bleibt in beiden Zustaenden benannt.
    expect(region.attributes('aria-label')).toBe('Reddit')
  })
})
