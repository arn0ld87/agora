import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
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

  // Fix #1713 (Befund 1): crumb.to wurde berechnet, aber nie gerendert —
  // Breadcrumbs waren reiner Text ohne Navigation.
  it('nicht-letzte Crumbs sind klickbare RouterLinks, der letzte bleibt Text', async () => {
    const { router, i18n } = build('/settings/llm-routing')
    await router.isReady()
    const w = mount(Breadcrumbs, { global: { plugins: [router, i18n] } })
    await w.vm.$nextTick()

    const crumbs = w.findAll('[data-crumb]')
    const firstLink = crumbs[0].find('a')
    expect(firstLink.exists()).toBe(true)
    expect(firstLink.text()).toBe('Einstellungen')
    expect(firstLink.attributes('href')).toBe('/settings')

    const lastLink = crumbs[crumbs.length - 1].find('a')
    expect(lastLink.exists()).toBe(false)
    expect(crumbs[crumbs.length - 1].text()).toBe('LLM-Routing')
  })

  it('zeigt die Kennung als kopierbare Marke neben dem Titel; Klick kopiert und meldet es', async () => {
    const { router, i18n } = build('/')
    await router.isReady()
    const writeText = vi.fn(async () => {})
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    const items = [{ label: 'Runs', to: '/' }, { label: 'Quartalsbericht', ident: 'sim_abc123' }]
    const w = mount(Breadcrumbs, { props: { items }, global: { plugins: [router, i18n] } })

    const ident = w.find('[data-testid="breadcrumb-ident"]')
    expect(ident.text()).toBe('sim_abc123')
    expect(ident.element.tagName).toBe('BUTTON')
    expect(w.findAll('[data-crumb]')[1].text()).toContain('Quartalsbericht')
    expect(w.find('[data-testid="breadcrumb-status"]').text()).toBe('')

    await ident.trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('sim_abc123')
    const status = w.find('[data-testid="breadcrumb-status"]')
    expect(status.attributes('aria-live')).toBe('polite')
    expect(status.text()).not.toBe('')
  })

  it('ohne ident gibt es keine Marke', async () => {
    const { router, i18n } = build('/')
    await router.isReady()
    const w = mount(Breadcrumbs, { props: { items: [{ label: 'Nur Titel' }] }, global: { plugins: [router, i18n] } })
    expect(w.find('[data-testid="breadcrumb-ident"]').exists()).toBe(false)
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
