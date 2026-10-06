/**
 * DemoPreviewStaticView — statische Erklaerkarte statt der echten Ansicht
 * fuer demoPreview:'static'-Routen (#1697, Teil B).
 *
 * App.vue rendert diese Komponente an Stelle der Route-Komponente — die
 * echte View mountet dabei gar nicht (kein Betreiber-Fetch). Prueft:
 * 1. AppShell (Sidebar + Topbar) bleibt vorhanden und bedienbar.
 * 2. Banner + statische Bullet-Liste je Route werden gerendert.
 * 3. Der Inhalt ist NICHT inert/ausgegraut (anders als DemoPreviewFrame).
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { makeTestRouter } from './testRouter'
import { defineComponent, h } from 'vue'
import AppShell from '../AppShell.vue'
import DemoPreviewStaticView from '../DemoPreviewStaticView.vue'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

async function mountStaticView(routeName: string) {
  const pinia = createPinia()
  setActivePinia(pinia)
  // testRouter kennt bereits alle Routen, die Sidebar.vue per RouterLink
  // referenziert (Dashboard, Runs, WorkspaceProviderKeys, ...).
  const router = makeTestRouter()
  await router.push({ name: routeName })
  await router.isReady()

  // Die Huelle liegt seit #1795 zentral in App.vue um die Ansicht (mit
  // demo-frame=false fuer die statische Vorschau) — hier nachgestellt.
  const Host = defineComponent({
    setup: () => () => h(AppShell, { demoFrame: false }, { default: () => h(DemoPreviewStaticView) }),
  })
  return mount(Host, { global: { plugins: [router, pinia, i18n] } })
}

describe('DemoPreviewStaticView', () => {
  it('liegt in der zentralen Huelle (Sidebar bleibt bedienbar, kein inert)', async () => {
    const wrapper = await mountStaticView('SettingsApiKeys')
    expect(wrapper.find('.app-shell').exists()).toBe(true)
    expect(wrapper.find('.app-shell__sidebar').exists()).toBe(true)
    expect(wrapper.find('.demo-preview-static__card').attributes('inert')).toBeUndefined()
  })

  it('zeigt Banner mit Link zu den eigenen Provider-Keys', async () => {
    const wrapper = await mountStaticView('SettingsApiKeys')
    const banner = wrapper.find('[role="status"]')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('Demo-Vorschau')
    const link = wrapper.find('.demo-preview-static__banner-link')
    expect(link.attributes('href')).toBe('/settings/providers')
  })

  it('zeigt die statischen Erlaeuterungen fuer SettingsApiKeys', async () => {
    const wrapper = await mountStaticView('SettingsApiKeys')
    expect(wrapper.text()).toContain('API-Schlüssel')
  })

  it('zeigt die statischen Erlaeuterungen fuer SettingsAuditLogs', async () => {
    const wrapper = await mountStaticView('SettingsAuditLogs')
    expect(wrapper.text()).toContain('Audit-Logs')
  })

  it('zeigt die statischen Erlaeuterungen fuer SettingsProfile', async () => {
    const wrapper = await mountStaticView('SettingsProfile')
    expect(wrapper.text()).toContain('Profil')
  })
})
