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

  it('zeigt den Zaehler neutral; ohne Zahl (null = unbekannt) gar keinen, auch kein "0"', async () => {
    await router.push('/')
    const withCount = mount(SidebarItem, { props: { label: 'Läufe', count: 0 }, global: { plugins: [router] } })
    expect(withCount.find('.sidebar-item__count').text()).toBe('0')
    const unknown = mount(SidebarItem, { props: { label: 'Läufe', count: null }, global: { plugins: [router] } })
    expect(unknown.find('.sidebar-item__count').exists()).toBe(false)
    const none = mount(SidebarItem, { props: { label: 'Vergleich' }, global: { plugins: [router] } })
    expect(none.find('.sidebar-item__count').exists()).toBe(false)
  })

  it('current erzwingt den aktiven Zustand gegen den Router (Query-Filter kennt er nicht)', async () => {
    await router.push('/runs')
    const off = mount(SidebarItem, { props: { label: 'Runs', to: { name: 'Runs' }, current: false }, global: { plugins: [router] } })
    expect(off.classes()).not.toContain('sidebar-item--active')
    expect(off.attributes('aria-current')).toBeUndefined()
    const on = mount(SidebarItem, { props: { label: 'Runs', to: { name: 'Home' }, current: true }, global: { plugins: [router] } })
    expect(on.classes()).toContain('sidebar-item--active')
    expect(on.attributes('aria-current')).toBe('page')
  })

  it('eingeklappt: kein sichtbares Label, aber aria-label und title mit Zaehler', async () => {
    await router.push('/')
    const wrapper = mount(SidebarItem, {
      props: { label: 'Braucht dich', glyph: '!', count: 2, collapsed: true, to: { name: 'Runs' } },
      global: { plugins: [router] },
    })
    expect(wrapper.find('.sidebar-item__label').exists()).toBe(false)
    expect(wrapper.find('.sidebar-item__count').exists()).toBe(false)
    expect(wrapper.attributes('aria-label')).toBe('Braucht dich, 2')
    expect(wrapper.attributes('title')).toBe('Braucht dich, 2')
  })

  it('Zustandspunkt: Zustand als Text fuer die Hilfstechnik, Punkt selbst aria-hidden', async () => {
    await router.push('/')
    const wrapper = mount(SidebarItem, {
      props: { label: 'System', tone: 'err', tooltip: 'Ein Dienst ist nicht erreichbar', to: { name: 'Runs' } },
      global: { plugins: [router] },
    })
    expect(wrapper.find('.sidebar-item__dot--err').attributes('aria-hidden')).toBe('true')
    expect(wrapper.find('.sidebar-item__sr').text()).toBe('Ein Dienst ist nicht erreichbar')
  })

  it('meldet click auch mit `to`, damit der mobile Drawer schliessen kann', async () => {
    await router.push('/')
    const wrapper = mount(SidebarItem, { props: { label: 'Runs', to: { name: 'Runs' } }, global: { plugins: [router] } })
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toBeTruthy()
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
