/**
 * Topbar — Smoke-Tests (Slice B, Design-v4).
 *
 * Prueft:
 * 1. Mountet ohne Crash.
 * 2. Breadcrumbs werden via Standard-Slot gerendert.
 * 3. Notification-Badge-Prop reicht durch.
 * 4. Kein Badge wenn notificationBadge=0.
 * 5. Custom-Crumbs-Slot ueberschreibt Default.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

import Topbar from '../Topbar.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/', component: { template: '<div/>' } }],
})

describe('Topbar', () => {
  it('mountet ohne Crash', async () => {
    await router.push('/')
    const wrapper = mount(Topbar, {
      global: { plugins: [router] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('rendert topbar-Klasse', async () => {
    await router.push('/')
    const wrapper = mount(Topbar, {
      global: { plugins: [router] },
    })
    expect(wrapper.classes()).toContain('topbar')
  })

  it('rendert Breadcrumbs-Inhalt wenn breadcrumbs-Prop gesetzt', async () => {
    await router.push('/')
    const wrapper = mount(Topbar, {
      props: {
        breadcrumbs: [{ label: 'Agora' }, { label: 'Dashboard' }],
      },
      global: { plugins: [router] },
    })
    expect(wrapper.text()).toContain('Agora')
    expect(wrapper.text()).toContain('Dashboard')
  })

  it('rendert Notification-Badge wenn notificationBadge > 0', async () => {
    await router.push('/')
    const wrapper = mount(Topbar, {
      props: { notificationBadge: 3 },
      global: { plugins: [router] },
    })
    expect(wrapper.find('.topbar__badge').exists()).toBe(true)
    expect(wrapper.find('.topbar__badge').text()).toBe('3')
  })

  it('rendert kein Badge wenn notificationBadge=0', async () => {
    await router.push('/')
    const wrapper = mount(Topbar, {
      props: { notificationBadge: 0 },
      global: { plugins: [router] },
    })
    expect(wrapper.find('.topbar__badge').exists()).toBe(false)
  })

  it('Custom-crumbs-Slot ueberschreibt Default-Breadcrumbs', async () => {
    await router.push('/')
    const wrapper = mount(Topbar, {
      slots: {
        crumbs: '<span class="custom-crumbs">Custom Crumbs</span>',
      },
      global: { plugins: [router] },
    })
    expect(wrapper.find('.custom-crumbs').exists()).toBe(true)
  })
})
