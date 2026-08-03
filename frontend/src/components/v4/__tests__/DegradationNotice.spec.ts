import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import DegradationNotice from '../DegradationNotice.vue'
import de from '@/i18n/locales/de.json'
import type { PipelineDegradationReport } from '@/contracts/pipelineDegradationContract'

/**
 * Issue #1029 — der Hinweis, der aus einem still degradierten Lauf einen
 * erkennbaren macht. Bewusst gegen die echten de.json-Texte gemountet:
 * ein fehlender i18n-Schlüssel würde sonst als roher Key durchrutschen und
 * der Test wäre trotzdem grün.
 */

function mountWith(report: PipelineDegradationReport) {
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } })
  return mount(DegradationNotice, { props: { report }, global: { plugins: [i18n] } })
}

const warningEvent = {
  kind: 'embedding_unavailable' as const,
  severity: 'warning' as const,
  detail: 'Batch-Embedding fehlgeschlagen, Vektoren bleiben leer.',
  occurred_at: '2026-08-02T20:00:00Z',
  occurrences: 1,
  context: {},
}

const blockingEvent = {
  kind: 'graph_below_threshold' as const,
  severity: 'blocking' as const,
  detail: 'Graph enthält 3 Entitäten und 0 Beziehungen.',
  occurred_at: '2026-08-02T20:01:00Z',
  occurrences: 1,
  context: { node_count: 3, edge_count: 0 },
}

describe('DegradationNotice', () => {
  it('rendert nichts, solange nichts ausgefallen ist', () => {
    const wrapper = mountWith({ schema_version: 1, events: [] })
    expect(wrapper.find('.degradation-notice').exists()).toBe(false)
  })

  it('zeigt Art, Ursache und Handlungsempfehlung', () => {
    const wrapper = mountWith({ schema_version: 1, events: [warningEvent] })
    const text = wrapper.text()

    expect(text).toContain('Semantische Suche nicht verfügbar')
    expect(text).toContain('Batch-Embedding fehlgeschlagen, Vektoren bleiben leer.')
    expect(text).toContain('Embedding-Dienst starten')
  })

  it('ist als Warnung markiert, wenn nichts blockiert', () => {
    const wrapper = mountWith({ schema_version: 1, events: [warningEvent] })
    const notice = wrapper.find('.degradation-notice')

    expect(notice.attributes('data-severity')).toBe('warning')
    expect(notice.text()).toContain('Durchgelaufen, aber mit Qualitätsverlust')
  })

  it('ein einziges blockierendes Ereignis färbt den ganzen Hinweis', () => {
    const wrapper = mountWith({ schema_version: 1, events: [warningEvent, blockingEvent] })
    const notice = wrapper.find('.degradation-notice')

    expect(notice.attributes('data-severity')).toBe('blocking')
    expect(notice.text()).toContain('Das Ergebnis reicht nicht zum Weiterarbeiten')
  })

  it('zeigt die Häufigkeit nur bei Wiederholung', () => {
    const single = mountWith({ schema_version: 1, events: [warningEvent] })
    expect(single.find('.degradation-notice__count').exists()).toBe(false)

    const repeated = mountWith({
      schema_version: 1,
      events: [{ ...warningEvent, occurrences: 12 }],
    })
    expect(repeated.find('.degradation-notice__count').text()).toContain('12')
  })

  it('listet jedes Ereignis einzeln auf', () => {
    const wrapper = mountWith({ schema_version: 1, events: [warningEvent, blockingEvent] })
    expect(wrapper.findAll('.degradation-notice__list li')).toHaveLength(2)
  })

  it('ist für Screenreader als Meldung ausgezeichnet', () => {
    const wrapper = mountWith({ schema_version: 1, events: [warningEvent] })
    const notice = wrapper.find('.degradation-notice')

    expect(notice.attributes('role')).toBe('alert')
    expect(notice.attributes('aria-live')).toBe('polite')
  })

  it('hat für jede Art einen übersetzten Text', () => {
    // Ohne diesen Test fällt eine neue Art erst im Betrieb als roher
    // i18n-Schlüssel auf.
    const kinds = ['embedding_unavailable', 'graph_below_threshold', 'persona_rule_based_fallback'] as const
    for (const kind of kinds) {
      const wrapper = mountWith({
        schema_version: 1,
        events: [{ ...warningEvent, kind }],
      })
      const text = wrapper.text()
      expect(text).not.toContain(`degradation.kind.${kind}`)
      expect(text).not.toContain(`degradation.action.${kind}`)
    }
  })
})
