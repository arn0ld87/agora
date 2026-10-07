/**
 * KI-Entwurf im Personasatz (#1807, E7-F3): Auftrag, Sperre, getrennte Fehler
 * und die Vorschau mit der SIM-Marke.
 *
 * Die Vorschau trägt „SIM" aus zwei Gründen: der Beispielbeitrag ist eine
 * **Simulation** und keine echte Äusserung, und er ist zugleich eine
 * Vorschau eines noch nicht gespeicherten Entwurfs. Wer ihn verwechselt,
 * hält eine erfundene Figur fuer einen Menschen mit einer Meinung.
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import type { PersonaDraftExamplePost } from '@/contracts/personaSetContract'
import { PersonaSetDetailTestId as Id } from '../detailTestIds'
import PersonaSetDraftPanel from '../PersonaSetDraftPanel.vue'

const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } })

function mountPanel(props: Partial<InstanceType<typeof PersonaSetDraftPanel>['$props']> = {}) {
  return mount(PersonaSetDraftPanel, {
    props: {
      drafting: false,
      providerError: false,
      actionError: null,
      example: null,
      locked: false,
      ...props,
    },
    global: { plugins: [i18n] },
  })
}

const EXAMPLE: PersonaDraftExamplePost = {
  content: 'Die Schichtplanung muss mit dem Betriebsrat abgestimmt sein.',
  network: 'twitter',
}

describe('PersonaSetDraftPanel', () => {
  it('sendet den getrimmten Auftrag und sonst nichts', async () => {
    const w = mountPanel()
    await w.find(`#${Id.draftBrief}`).setValue('  Betriebsratin aus Bremen  ')
    await w.find(`[data-testid="${Id.draftSubmit}"]`).trigger('submit')

    expect(w.emitted('draft')).toEqual([['Betriebsratin aus Bremen']])
  })

  it('lässt keinen leeren Auftrag zu', async () => {
    const w = mountPanel()
    await w.find(`#${Id.draftBrief}`).setValue('   ')
    await w.find(`[data-testid="${Id.draftSubmit}"]`).trigger('submit')

    expect(w.emitted('draft')).toBeUndefined()
  })

  it('sperrt den Auftrag, solange er läuft', async () => {
    const w = mountPanel({ drafting: true })
    await w.find(`#${Id.draftBrief}`).setValue('Bremen')

    expect(w.find(`[data-testid="${Id.draftSubmit}"]`).attributes('disabled')).toBeDefined()
    expect(w.find(`#${Id.draftBrief}`).attributes('disabled')).toBeDefined()
  })

  it('nimmt einen gesperrten Satz nicht an und bietet den Ausweg an', async () => {
    const w = mountPanel({ locked: true })

    expect(w.find(`[data-testid="${Id.draftSubmit}"]`).exists()).toBe(false)
    // Der Ausweg ist der Hinweis: duplizieren. Ohne ihn wäre die Sperre eine
    // Sackgasse ohne Erklärung.
    expect(w.find(`[data-testid="${Id.draftLocked}"]`).text()).toContain('duplizieren')
  })

  it('trennt den Anbieterfehler vom Fehler am Auftrag', async () => {
    const provider = mountPanel({ providerError: true, actionError: '503 vom Anbieter' })
    // Beide Nachrichten liegen vor; die Oberfläche zeigt genau eine, sonst
    // wüsste der Nutzer nicht, ob er den Brief ändern oder warten soll.
    expect(provider.find(`[data-testid="${Id.draftProviderError}"]`).exists()).toBe(true)
    expect(provider.find(`[data-testid="${Id.draftActionError}"]`).exists()).toBe(false)
    expect(provider.find(`[data-testid="${Id.draftProviderError}"]`).text()).toContain('neuer Versuch')

    const own = mountPanel({ providerError: false, actionError: 'Brief ist leer' })
    expect(own.find(`[data-testid="${Id.draftProviderError}"]`).exists()).toBe(false)
    expect(own.find(`[data-testid="${Id.draftActionError}"]`).text()).toBe('Brief ist leer')
  })

  it('meldet den Anbieterfehler als Alarm und nicht als Nebenhinweis', () => {
    const w = mountPanel({ providerError: true })
    expect(w.find(`[data-testid="${Id.draftProviderError}"]`).attributes('role')).toBe('alert')
  })

  it('zeigt die Vorschau mit SIM-Marke und Netzwerk', () => {
    const w = mountPanel({ example: EXAMPLE })
    const preview = w.find(`[data-testid="${Id.draftPreview}"]`)

    expect(preview.exists()).toBe(true)
    expect(preview.text()).toContain(EXAMPLE.content)
    expect(preview.text()).toContain('twitter')
    // „SIM" ist Text, nicht nur Symbol: ohne Text bleibt die Vorschau eine
    // Behauptung ueber eine Figur.
    expect(preview.text()).toContain('SIM')
  })

  it('verwirft die Vorschau auf Zuruf', async () => {
    const w = mountPanel({ example: EXAMPLE })
    await w.find(`[data-testid="${Id.draftDismiss}"]`).trigger('click')

    expect(w.emitted('dismiss')).toHaveLength(1)
  })

  it('zeigt keine Vorschau ohne Beispielbeitrag', () => {
    const w = mountPanel({ example: null })
    // Kein Beispielbeitrag heißt: die Vorschau ist leer. Eine leere Flaeche mit
    // Rahmen wuerde wie ein Ladezustand aussehen.
    expect(w.find(`[data-testid="${Id.draftPreview}"]`).exists()).toBe(false)
  })

  it('gibt die Vorschau frei, sobald der Auftrag wieder leer ist', async () => {
    const w = mountPanel()
    await w.find(`#${Id.draftBrief}`).setValue('Bremen')
    expect(w.find(`[data-testid="${Id.draftSubmit}"]`).attributes('disabled')).toBeUndefined()

    await w.find(`#${Id.draftBrief}`).setValue('')
    expect(w.find(`[data-testid="${Id.draftSubmit}"]`).attributes('disabled')).toBeDefined()
  })
})
