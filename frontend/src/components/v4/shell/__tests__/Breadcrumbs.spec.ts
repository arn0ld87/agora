import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'
import Breadcrumbs from '../Breadcrumbs.vue'

function build(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Dashboard', component: { template: '<div/>' } },
      {
        path: '/settings',
        name: 'Settings',
        component: { template: '<div/>' },
        children: [{ path: 'llm-routing', name: 'SettingsLlmRouting', component: { template: '<div/>' } }],
      },
    ],
  })
  const i18n = createI18n({
    locale: 'de',
    messages: { de: { nav: { Dashboard: 'Dashboard', Settings: 'Einstellungen', SettingsLlmRouting: 'LLM-Routing' } } },
  })
  router.push(path)
  return { router, i18n }
}

describe('Breadcrumbs', () => {
  it('zeigt einen Crumb für Dashboard', async () => {
    const { router, i18n } = build('/')
    await router.isReady()
    const w = mount(Breadcrumbs, { global: { plugins: [router, i18n] } })
    expect(w.findAll('[data-crumb]').length).toBe(1)
    expect(w.text()).toContain('Dashboard')
  })

  it('zeigt Trail Einstellungen > LLM-Routing', async () => {
    const { router, i18n } = build('/settings/llm-routing')
    await router.isReady()
    const w = mount(Breadcrumbs, { global: { plugins: [router, i18n] } })
    await w.vm.$nextTick()
    const crumbs = w.findAll('[data-crumb]')
    expect(crumbs.length).toBe(2)
    expect(crumbs[0].text()).toContain('Einstellungen')
    expect(crumbs[1].text()).toContain('LLM-Routing')
  })

  it('letzter Crumb hat aria-current="page"', async () => {
    const { router, i18n } = build('/settings/llm-routing')
    await router.isReady()
    const w = mount(Breadcrumbs, { global: { plugins: [router, i18n] } })
    await w.vm.$nextTick()
    const crumbs = w.findAll('[data-crumb]')
    expect(crumbs[crumbs.length - 1].attributes('aria-current')).toBe('page')
  })

  it('Props-Fallback: explizite items überschreiben Auto-Derive', async () => {
    const { router, i18n } = build('/')
    await router.isReady()
    const items = [{ label: 'Custom A' }, { label: 'Custom B' }]
    const w = mount(Breadcrumbs, { props: { items }, global: { plugins: [router, i18n] } })
    expect(w.text()).toContain('Custom A')
    expect(w.text()).toContain('Custom B')
  })
})
