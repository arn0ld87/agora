/**
 * ShelfLayout — Komponenten-Tests (#1795, Ticket 5; ex ShellRoot-Spec, Block B3/B4).
 *
 * Prueft die Inhaltsflaeche der Ablage (die Huelle selbst ist AppShell):
 * 1. Rendert die Slot-Inhalte (shelf/dossier).
 * 2. Der Stapel-Zurueck-Knopf emittiert select(null), auch auf schmal.
 * 3. Unter 1100px traegt je nach Auswahl nur Shelf oder Dossier die Flaeche.
 *
 * Selektoren ausschliesslich ueber ShellTestId (src/contracts/testIds.ts).
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { ShellTestId } from '../../../contracts/testIds'
import type { ShelfObject } from '../../../types/shelf'
import ShelfLayout from '../ShelfLayout.vue'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

function makeObject(overrides: Partial<ShelfObject> = {}): ShelfObject {
  return {
    kind: 'lauf',
    id: 'sim_1',
    title: 'Testlauf',
    statusLine: 'Laeuft',
    updatedAt: '2026-08-18T10:00:00Z',
    metaId: 'sim_1',
    nextAction: null,
    active: null,
    ...overrides,
  }
}

function mountLayout(current: ShelfObject | null = null) {
  return mount(ShelfLayout, {
    props: { current },
    slots: {
      shelf: '<div data-testid="shelf-slot-marker">shelf-inhalt</div>',
      dossier: '<div data-testid="dossier-slot-marker">dossier-inhalt</div>',
    },
    global: { plugins: [i18n] },
  })
}

describe('ShelfLayout', () => {
  it('mountet ohne Crash und rendert die Slot-Inhalte', () => {
    const wrapper = mountLayout()
    expect(wrapper.find(`[data-testid="${ShellTestId.root}"]`).exists()).toBe(true)
    expect(wrapper.find('[data-testid="shelf-slot-marker"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="dossier-slot-marker"]').exists()).toBe(true)
  })

  it('bringt keine eigene Huelle mit (keine Kopfzeile, keine Palette, kein Toast)', () => {
    const wrapper = mountLayout(makeObject())
    expect(wrapper.find('header').exists()).toBe(false)
    expect(wrapper.find(`[data-testid="${ShellTestId.cmdkTrigger}"]`).exists()).toBe(false)
    expect(wrapper.find(`[data-testid="${ShellTestId.logsTrigger}"]`).exists()).toBe(false)
    expect(wrapper.find(`[data-testid="${ShellTestId.userMenu}"]`).exists()).toBe(false)
    expect(wrapper.find(`[data-testid="${ShellTestId.undoToast}"]`).exists()).toBe(false)
  })

  it('der Stapel-Zurueck-Knopf emittiert select(null)', async () => {
    const wrapper = mountLayout(makeObject())
    await wrapper.find(`[data-testid="${ShellTestId.stackBack}"]`).trigger('click')

    expect(wrapper.emitted('select')?.[0]).toEqual([null])
  })

  it('blendet ohne Auswahl das Dossier aus und zeigt die Ablage', () => {
    const w = mountLayout(null)
    expect(w.find(`[data-testid="${ShellTestId.panelShelf}"]`).attributes('data-hidden-narrow')).toBe('false')
    expect(w.find(`[data-testid="${ShellTestId.panelDossier}"]`).attributes('data-hidden-narrow')).toBe('true')
  })

  it('dreht das mit einer Auswahl um — dann traegt das Dossier die Flaeche', () => {
    const w = mountLayout(makeObject())
    expect(w.find(`[data-testid="${ShellTestId.panelShelf}"]`).attributes('data-hidden-narrow')).toBe('true')
    expect(w.find(`[data-testid="${ShellTestId.panelDossier}"]`).attributes('data-hidden-narrow')).toBe('false')
  })
})
