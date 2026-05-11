/**
 * SidebarItem — Smoke-Tests (Slice B, Design-v4).
 *
 * Prueft:
 * 1. Active-Style-Klasse bei active=true.
 * 2. Keine Active-Klasse bei active=false.
 * 3. Badge wird gerendert wenn badge>0.
 * 4. RouterLink wird genutzt wenn to gesetzt.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

import SidebarItem from '../SidebarItem.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', name: 'Home', component: { template: '<div/>' } },
    { path: '/runs', name: 'Runs', component: { template: '<div/>' } },
  ],
})

describe('SidebarItem', () => {
  it('mountet ohne Crash', async () => {
    await router.push('/')
    const wrapper = mount(SidebarItem, {
      props: { label: 'Dashboard', icon: 'home' },
      global: { plugins: [router] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('rendert Label-Text', async () => {
    await router.push('/')
    const wrapper = mount(SidebarItem, {
      props: { label: 'Dashboard' },
      global: { plugins: [router] },
    })
    expect(wrapper.text()).toContain('Dashboard')
  })

  it('setzt sidebar-item--active Klasse bei active=true', async () => {
    await router.push('/')
    const wrapper = mount(SidebarItem, {
      props: { label: 'Dashboard', active: true },
      global: { plugins: [router] },
    })
    expect(wrapper.classes()).toContain('sidebar-item--active')
  })

  it('hat keine sidebar-item--active Klasse bei active=false', async () => {
    await router.push('/')
    const wrapper = mount(SidebarItem, {
      props: { label: 'Runs', active: false },
      global: { plugins: [router] },
    })
    expect(wrapper.classes()).not.toContain('sidebar-item--active')
  })

  it('rendert Badge wenn badge > 0', async () => {
    await router.push('/')
    const wrapper = mount(SidebarItem, {
      props: { label: 'Runs', badge: 5 },
      global: { plugins: [router] },
    })
    expect(wrapper.find('.sidebar-item__badge').exists()).toBe(true)
    expect(wrapper.find('.sidebar-item__badge').text()).toBe('5')
  })

  it('rendert kein Badge wenn badge=0', async () => {
    await router.push('/')
    const wrapper = mount(SidebarItem, {
      props: { label: 'Runs', badge: 0 },
      global: { plugins: [router] },
    })
    expect(wrapper.find('.sidebar-item__badge').exists()).toBe(false)
  })

  it('nutzt RouterLink wenn to gesetzt', async () => {
    await router.push('/')
    const wrapper = mount(SidebarItem, {
      props: { label: 'Runs', to: { name: 'Runs' } },
      global: { plugins: [router] },
    })
    // RouterLink rendert als <a>
    expect(wrapper.element.tagName.toLowerCase()).toBe('a')
  })

  it('nutzt div wenn to nicht gesetzt', async () => {
    await router.push('/')
    const wrapper = mount(SidebarItem, {
      props: { label: 'Placeholder' },
      global: { plugins: [router] },
    })
    expect(wrapper.element.tagName.toLowerCase()).toBe('div')
  })
})
