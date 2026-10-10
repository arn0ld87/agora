import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import GraphOriginMark from '../GraphOriginMark.vue'
import { GraphEditTestId } from '@/contracts/testIds'
import { makeI18n } from './fixtures'

function mountMark(origin: 'manual' | 'edited' | null, changedAt: string | null = null) {
  return mount(GraphOriginMark, {
    props: { origin, changedAt },
    global: { plugins: [makeI18n()] },
  })
}

describe('GraphOriginMark', () => {
  it('zeigt die Herkunft als Text und als Symbol, nie nur als Farbe', () => {
    const manual = mountMark('manual')
    expect(manual.get(`[data-testid="${GraphEditTestId.markManual}"]`).text()).toContain('manuell')
    // Text allein waere eine Farblose Marke; das Symbol macht sie auch fuer
    // Farbfehlsichtige und im Schwarz-Weiss-Druck unterscheidbar.
    expect(manual.get(`[data-testid="${GraphEditTestId.markManual}"] [aria-hidden="true"]`).text()).toBe('✎')
    expect(manual.text()).not.toContain('extrahiert')

    const edited = mountMark('edited')
    expect(edited.get(`[data-testid="${GraphEditTestId.markEdited}"]`).text()).toContain('bearbeitet')
    expect(edited.get(`[data-testid="${GraphEditTestId.markEdited}"] [aria-hidden="true"]`).text()).toBe('✎')
  })

  it('nennt bei bearbeitet die Aenderung, bei extrahiert die Herkunft', () => {
    expect(mountMark('edited', '2026-10-07').text()).toContain('Geändert am 2026-10-07')
    expect(mountMark('manual', '2026-10-07').text()).not.toContain('Geändert am')
  })

  it('unterscheidet die drei Herkünfte an Testkennung und Text; kein Datum ohne Änderungsstempel', () => {
    const edited = mountMark('edited')
    expect(edited.find(`[data-testid="${GraphEditTestId.markEdited}"]`).exists()).toBe(true)
    expect(edited.find(`[data-testid="${GraphEditTestId.markManual}"]`).exists()).toBe(false)
    expect(edited.find(`[data-testid="${GraphEditTestId.markExtracted}"]`).exists()).toBe(false)
    expect(edited.text()).not.toContain('Geändert am')
    const manual = mountMark('manual')
    expect(manual.find(`[data-testid="${GraphEditTestId.markEdited}"]`).exists()).toBe(false)
    expect(manual.text()).not.toContain('bearbeitet')
  })

  it('trägt die Bedeutung im Text; das Symbol ist auch bei extrahiert für Hilfstechnik verborgen', () => {
    for (const origin of ['manual', 'edited', null] as const) {
      const wrapper = mountMark(origin)
      const symbol = wrapper.get('[aria-hidden="true"]')
      expect(symbol.text()).toBe('✎')
      expect(wrapper.text().replace('✎', '').trim().length).toBeGreaterThan(0)
    }
  })

  it('zeigt ohne Merkmal extrahiert statt nichts', () => {
    const wrapper = mountMark(null)
    expect(wrapper.get(`[data-testid="${GraphEditTestId.markExtracted}"]`).text()).toContain('extrahiert')
    expect(wrapper.find(`[data-testid="${GraphEditTestId.markManual}"]`).exists()).toBe(false)
  })
})
