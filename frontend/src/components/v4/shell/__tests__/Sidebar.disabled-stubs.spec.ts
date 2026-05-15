/**
 * Sidebar — disabled Stub-Items (smoke #5).
 *
 * Prueft:
 * 1. projects/datasets/templates/monitoring haben aria-disabled="true".
 * 2. Diese Items rendern keinen RouterLink mit to="/dashboard".
 * 3. Der Tooltip-Text (sidebar.disabledTooltip) wird via title-Attribut gerendert.
 * 4. Dashboard und Runs sind NICHT disabled.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { makeTestRouter } from './testRouter'
import Sidebar from '../Sidebar.vue'

const lsMock = (() => {
  const s: Record<string, string> = {}
  return {
    getItem: (k: string) => s[k] ?? null,
    setItem: (k: string, v: string) => { s[k] = v },
    removeItem: (k: string) => { delete s[k] },
    clear: () => { Object.keys(s).forEach((k) => { delete s[k] }) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: lsMock, writable: true })

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })
const router = makeTestRouter()

const STUB_IDS = ['projects', 'datasets', 'templates', 'monitoring']
const ACTIVE_IDS = ['dashboard', 'runs']

describe('Sidebar disabled stub nav items (smoke #5)', () => {
  beforeEach(() => {
    lsMock.clear()
    setActivePinia(createPinia())
  })

  async function mountSidebar(props: Record<string, unknown> = {}) {
    await router.push('/')
    return mount(Sidebar, {
      props,
      global: { plugins: [router, i18n] },
    })
  }

  it('stub-Items haben aria-disabled="true"', async () => {
    const wrapper = await mountSidebar()
    const disabledItems = wrapper.findAll('[aria-disabled="true"]')
    expect(disabledItems.length).toBe(STUB_IDS.length)
  })

  it('stub-Items rendern DE-Locale-Labels', async () => {
    const wrapper = await mountSidebar()
    const text = wrapper.text()
    expect(text).toContain('Projekte')
    expect(text).toContain('Datensätze')
    expect(text).toContain('Vorlagen')
    expect(text).toContain('Monitoring')
  })

  it('stub-Items haben tooltip mit sidebar.disabledTooltip ("Bald verfügbar")', async () => {
    const wrapper = await mountSidebar()
    const disabledItems = wrapper.findAll('[aria-disabled="true"]')
    for (const item of disabledItems) {
      expect(item.attributes('title')).toBe('Bald verfügbar')
    }
  })

  it('stub-Items routen nicht nach /dashboard (kein RouterLink with to=/dashboard)', async () => {
    const wrapper = await mountSidebar()
    // RouterLink rendert als <a>; disabled items rendern als <span>
    // Sicherstellen dass kein stub-Item als RouterLink mit to=/dashboard endet
    const routerLinks = wrapper.findAllComponents({ name: 'RouterLink' })
    const dashboardLinks = routerLinks.filter((l) => {
      const to = l.props('to') as { name?: string; path?: string } | string | undefined
      if (!to) return false
      if (typeof to === 'string') return to === '/dashboard'
      if (typeof to === 'object' && 'name' in to) return to.name === 'Dashboard'
      return false
    })
    // Nur das Dashboard-Item selbst darf auf Dashboard routen — nicht die Stubs
    expect(dashboardLinks.length).toBeLessThanOrEqual(1)

    // Sicherstellen: keiner der disabled items ist ein RouterLink
    const disabledRouterLinks = routerLinks.filter((l) => {
      const to = l.props('to') as { path?: string } | undefined
      if (!to || typeof to !== 'object') return false
      const path = (to as { path?: string }).path || ''
      return ['#projects', '#datasets', '#templates', '#monitoring'].includes(path)
    })
    expect(disabledRouterLinks.length).toBe(0)
  })

  it('dashboard und runs sind NICHT disabled', async () => {
    const wrapper = await mountSidebar()
    const allItems = wrapper.findAll('.sidebar-item')
    const activableItems = allItems.filter((el) => {
      const ariaDisabled = el.attributes('aria-disabled')
      return !ariaDisabled || ariaDisabled !== 'true'
    })
    // mind. dashboard + runs sind nicht disabled
    expect(activableItems.length).toBeGreaterThanOrEqual(ACTIVE_IDS.length)
  })

  it('disabled-Items haben Klasse sidebar-item--disabled', async () => {
    const wrapper = await mountSidebar()
    const disabledCssItems = wrapper.findAll('.sidebar-item--disabled')
    expect(disabledCssItems.length).toBe(STUB_IDS.length)
  })
})
