/**
 * SettingsOverlay — Redesign PR 9 (`ui(settings)`).
 *
 * Ersetzt die pro-Seite-Breadcrumbs aller `/settings/*`-Routen durch eine
 * gemeinsame Sektionsliste. Coverage:
 *  1. mountet ohne Crash, zeigt Titel + Slot-Inhalt
 *  2. Sektionsliste zeigt alle acht Nav-Items (Review PR #1439: LLM-Routing
 *     und Audit-Log gehoeren dazu, sonst hat keine View auf diesen Routen
 *     eine aktive Sektion)
 *  3. markiert die aktuelle Route mit aria-current="page"
 *  4. LLM-Routing UND Audit-Log stehen in der Liste und werden als aktiv
 *     markiert, wenn ihre Route aktiv ist
 *  5. "Zurück"-Button ruft router.back() auf
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

  it('zeigt alle acht Sektionen der Nav-Liste', async () => {
    const { wrapper } = await mountOverlay('/settings/general')
    const links = wrapper.findAll('nav a')
    expect(links).toHaveLength(8)
    const labels = links.map((l) => l.text())
    expect(labels).toEqual([
      'Allgemein',
      'Integrationen',
      'Profil',
      'API-Schlüssel',
      'LLM-Anbieter',
      'Embedding-Konfiguration',
      'LLM-Routing',
      'Audit-Logs',
    ])
  })

  it('markiert die aktuelle Route mit aria-current="page"', async () => {
    const { wrapper } = await mountOverlay('/settings/integrations')
    const active = wrapper.find('a[aria-current="page"]')
    expect(active.exists()).toBe(true)
    expect(active.text()).toBe('Integrationen')
  })

  it('LLM-Routing und Audit-Log stehen in der Liste und werden als aktiv markiert (Review PR #1439)', async () => {
    const { wrapper } = await mountOverlay('/settings/llm-routing')
    const labels = wrapper.findAll('nav a').map((l) => l.text())
    expect(labels).toContain('LLM-Routing')
    expect(labels).toContain('Audit-Logs')
    const active = wrapper.find('a[aria-current="page"]')
    expect(active.exists()).toBe(true)
    expect(active.text()).toBe('LLM-Routing')
  })

  it('"Zurück"-Button ruft router.back() auf', async () => {
    const { wrapper, backSpy } = await mountOverlay('/settings/general')
    await wrapper.find('button').trigger('click')
    expect(backSpy).toHaveBeenCalled()
  })
})
