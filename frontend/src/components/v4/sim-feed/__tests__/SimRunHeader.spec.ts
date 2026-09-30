/**
 * SimRunHeader — Slice UI-2b (#1713), docs/design/simulation-feed.md §2.3.
 * loading (Werte "—", aria-busy), degraded (Chip sichtbar, nie als Erfolg
 * gefaerbt) und der Live-Punkt je Stream-Zustand.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, te: () => true }),
}))

import SimRunHeader from '../SimRunHeader.vue'

function baseProps() {
  return {
    simulationId: 'sim-1',
    currentRound: 2,
    totalRounds: 5,
    simTime: '2026-05-15T12:00:00Z',
    postCount: 42,
    streamState: 'open' as const,
  }
}

describe('SimRunHeader', () => {
  it('gruppiert den Kopf und begrenzt role=status auf den Stream', () => {
    const w = mount(SimRunHeader, { props: baseProps() })
    const root = w.get('[role="group"]')
    expect(root.attributes('aria-busy')).toBe('false')
    expect(root.text()).toContain('feed.header.round')
    expect(w.get('[role="status"]').classes()).toContain('srh-stream')
  })

  it('loading=true ersetzt Rundenanzeige/Zeit/Anzahl durch "—" und setzt aria-busy', () => {
    const w = mount(SimRunHeader, { props: { ...baseProps(), loading: true } })
    const root = w.get('[role="group"]')
    expect(root.attributes('aria-busy')).toBe('true')
    expect(w.find('.srh-round').text()).toBe('—')
    expect(w.find('.srh-simtime').text()).toBe('—')
    expect(w.find('.srh-count').text()).toBe('—')
  })

  it('currentRound=null zeigt roundUnknown statt "Runde null"', () => {
    const w = mount(SimRunHeader, { props: { ...baseProps(), currentRound: null } })
    expect(w.find('.srh-round').text()).toBe('feed.header.roundUnknown')
  })

  it('degradation zeigt einen Chip mit role=alert, keine Erfolgsfarbe', () => {
    const w = mount(SimRunHeader, {
      props: {
        ...baseProps(),
        degradation: { kind: 'stream_lost', hint: 'Live-Verbindung verloren.' },
      },
    })
    const chip = w.get('[role="alert"]')
    expect(chip.classes()).toContain('srh-degradation')
  })

  it('ohne degradation gibt es keinen alert-Chip', () => {
    const w = mount(SimRunHeader, { props: baseProps() })
    expect(w.find('[role="alert"]').exists()).toBe(false)
  })

  it.each([
    ['open', 'feed.header.streamOpen'],
    ['connecting', 'feed.header.streamConnecting'],
    ['reconnecting', 'feed.header.streamReconnecting'],
    ['closed', 'feed.header.streamClosed'],
    ['ended', 'feed.header.streamEnded'],
  ] as const)('streamState=%s zeigt den passenden Label-Key', (state, expectedKey) => {
    const w = mount(SimRunHeader, { props: { ...baseProps(), streamState: state } })
    expect(w.find('.srh-stream').text()).toBe(expectedKey)
    expect(w.get('.srh-live-dot').attributes('data-state')).toBe(state)
  })
})
