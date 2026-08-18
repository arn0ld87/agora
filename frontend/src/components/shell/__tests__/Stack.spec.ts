/**
 * Stack — Komponenten-Tests (Block B3).
 *
 * Prueft:
 * 1. Zurueck-Knopf ist deaktiviert ohne aktuelles Objekt, aktiv mit einem.
 * 2. Klick auf den (aktivierten) Zurueck-Knopf emittiert select(null).
 * 3. Ein gesetztes current-Objekt landet im sessionStorage-Ring (Rueckweg-Chronik).
 *
 * Die Pill-Chronik selbst traegt keine eigenen data-testid (nur
 * ShellTestId.stack/stackBack existieren) — sie wird daher bewusst nicht
 * per Klick getestet (siehe Abschlussbericht).
 *
 * Selektoren ausschliesslich ueber ShellTestId (src/contracts/testIds.ts).
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { ShellTestId } from '../../../contracts/testIds'
import type { ShelfObject } from '../../../types/shelf'
import Stack from '../Stack.vue'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

function makeObject(overrides: Partial<ShelfObject> = {}): ShelfObject {
  return {
    kind: 'lauf',
    id: 'sim_1',
    title: 'Testlauf eins',
    statusLine: 'Laeuft',
    updatedAt: '2026-08-18T10:00:00Z',
    metaId: 'sim_1',
    nextAction: null,
    active: null,
    ...overrides,
  }
}

describe('Stack', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  it('Zurueck-Knopf ist deaktiviert ohne current und aktiv mit einem current-Objekt', () => {
    const withoutCurrent = mount(Stack, { props: { current: null }, global: { plugins: [i18n] } })
    expect(withoutCurrent.find(`[data-testid="${ShellTestId.stackBack}"]`).attributes('disabled')).toBeDefined()

    const withCurrent = mount(Stack, { props: { current: makeObject() }, global: { plugins: [i18n] } })
    expect(withCurrent.find(`[data-testid="${ShellTestId.stackBack}"]`).attributes('disabled')).toBeUndefined()
  })

  it('Klick auf den aktivierten Zurueck-Knopf emittiert select(null)', async () => {
    const wrapper = mount(Stack, { props: { current: makeObject() }, global: { plugins: [i18n] } })
    await wrapper.find(`[data-testid="${ShellTestId.stackBack}"]`).trigger('click')

    expect(wrapper.emitted('select')).toEqual([[null]])
  })

  it('ein gesetztes current-Objekt landet im sessionStorage-Ring', () => {
    const obj = makeObject({ kind: 'bericht', id: 'report_9', title: 'Bericht Neun' })
    mount(Stack, { props: { current: obj }, global: { plugins: [i18n] } })

    const raw = sessionStorage.getItem('agora.shelf.stack')
    expect(raw).not.toBeNull()
    const ring = JSON.parse(raw as string) as Array<{ kind: string; id: string; title: string }>
    expect(ring).toContainEqual({ kind: 'bericht', id: 'report_9', title: 'Bericht Neun' })
  })
})
