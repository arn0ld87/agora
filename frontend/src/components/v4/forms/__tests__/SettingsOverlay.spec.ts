/**
 * SettingsOverlay — Redesign PR 9 (`ui(settings)`).
 *
 * Ersetzt die pro-Seite-Breadcrumbs aller `/settings/*`-Routen durch eine
 * gemeinsame Sektionsliste. Coverage:
 *  1. mountet ohne Crash, zeigt Titel + Slot-Inhalt
 *  2. Sektionsliste zeigt alle sechs Nav-Items
 *  3. markiert die aktuelle Route mit aria-current="page"
 *  4. LLM-Routing / Audit-Log stehen NICHT in der Liste (nur Deep-Link)
 *  5. Deep-Link-Hinweistext ist sichtbar
 *  6. "Zurück"-Button ruft router.back() auf
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { makeTestRouter } from '@/components/v4/shell/__tests__/testRouter'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import SettingsOverlay from '../SettingsOverlay.vue'

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'de',
    fallbackLocale: 'en',
    messages: { de, en },
  })
}

async function mountOverlay(path: string) {
  const router = makeTestRouter()
  const i18n = makeI18n()
  await router.push(path)
  await router.isReady()
  const backSpy = vi.spyOn(router, 'back')
  const wrapper = mount(SettingsOverlay, {
    global: { plugins: [router, i18n] },
    slots: { default: '<p class="slot-probe">Inhalt</p>' },
  })
  await flushPromises()
  return { wrapper, backSpy }
}

describe('SettingsOverlay', () => {
  it('mountet ohne Crash, zeigt Titel + Slot-Inhalt', async () => {
    const { wrapper } = await mountOverlay('/settings/general')
    expect(wrapper.find('h1').text()).toBe('Einstellungen')
    expect(wrapper.find('.slot-probe').exists()).toBe(true)
  })

  it('zeigt alle sechs Sektionen der Nav-Liste', async () => {
    const { wrapper } = await mountOverlay('/settings/general')
    const links = wrapper.findAll('nav a')
    expect(links).toHaveLength(6)
    const labels = links.map((l) => l.text())
    expect(labels).toEqual([
      'Allgemein',
      'Integrationen',
      'Profil',
      'API-Schlüssel',
      'LLM-Anbieter',
      'Embedding-Konfiguration',
    ])
  })

  it('markiert die aktuelle Route mit aria-current="page"', async () => {
    const { wrapper } = await mountOverlay('/settings/integrations')
    const active = wrapper.find('a[aria-current="page"]')
    expect(active.exists()).toBe(true)
    expect(active.text()).toBe('Integrationen')
  })

  it('LLM-Routing und Audit-Log stehen nicht in der Liste', async () => {
    const { wrapper } = await mountOverlay('/settings/llm-routing')
    const labels = wrapper.findAll('nav a').map((l) => l.text())
    expect(labels).not.toContain('LLM Routing')
    expect(labels).not.toContain('Audit Logs')
    // Keine der sechs Sektionen ist aktiv, weil diese Route nicht gelistet ist.
    expect(wrapper.find('a[aria-current="page"]').exists()).toBe(false)
  })

  it('zeigt den Deep-Link-Hinweistext', async () => {
    const { wrapper } = await mountOverlay('/settings/general')
    expect(wrapper.text()).toContain('LLM-Routing und Audit-Log bleiben per Deep-Link erreichbar')
  })

  it('"Zurück"-Button ruft router.back() auf', async () => {
    const { wrapper, backSpy } = await mountOverlay('/settings/general')
    await wrapper.find('button').trigger('click')
    expect(backSpy).toHaveBeenCalled()
  })
})
