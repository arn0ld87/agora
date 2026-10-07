import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import FeedNotices from '../FeedNotices.vue'
import FeedSidebar from '../FeedSidebar.vue'
import PersonaCard from '../PersonaCard.vue'
import RoundPanel from '../RoundPanel.vue'
import RoundScrubber from '../RoundScrubber.vue'
import { i18n } from './fixtures'

const global = { plugins: [i18n] }

describe('RoundScrubber', () => {
  it('Live setzt den Cursor auf null, der Regler auf eine Runde', async () => {
    const w = mount(RoundScrubber, { props: { cursor: 4, maxRound: 9, pendingCount: 0 }, global })
    expect(w.get('[data-testid="scrubber-live"]').attributes('aria-pressed')).toBe('false')
    expect(w.get('[data-testid="scrubber-status"]').text()).toBe('Gezeigt bis Runde 4 von 9')
    await w.get('[data-testid="scrubber-live"]').trigger('click')
    expect(w.emitted('update:cursor')?.[0]).toEqual([null])
    const range = w.get('[data-testid="scrubber-range"]')
    expect(range.attributes('max')).toBe('9')
    await range.setValue('6')
    expect(w.emitted('update:cursor')?.[1]).toEqual([6])
  })

  it('zeigt die Pille nur bei gesammelten Beiträgen und meldet flush', async () => {
    const w = mount(RoundScrubber, { props: { cursor: 2, maxRound: 9, pendingCount: 0 }, global })
    expect(w.find('[data-testid="scrubber-pill"]').exists()).toBe(false)
    await w.setProps({ pendingCount: 3 })
    const pill = w.get('[data-testid="scrubber-pill"]')
    expect(pill.text()).toBe('3 neue Beiträge anzeigen')
    await pill.trigger('click')
    expect(w.emitted('flush')).toHaveLength(1)
  })

  it('nennt fehlende Rundenangaben, statt einen leeren Regler zu zeigen', () => {
    const w = mount(RoundScrubber, { props: { cursor: null, maxRound: null, pendingCount: 0 }, global })
    expect(w.find('[data-testid="scrubber-range"]').exists()).toBe(false)
    expect(w.get('[data-testid="scrubber-status"]').text()).toContain('Noch keine Rundenangabe')
  })
})

describe('FeedSidebar', () => {
  const props = {
    network: 'twitter' as const,
    persona: '',
    round: null,
    query: '',
    personaOptions: [{ id: '0', name: 'Anna' }],
    roundOptions: [1, 2],
    contestedQuestion: 'Soll es eine Abgabe geben?',
  }

  it('meldet Netzwerkwechsel und Filteränderungen', async () => {
    const w = mount(FeedSidebar, { props, global })
    expect(w.get('[data-testid="feed-network-twitter"]').attributes('aria-pressed')).toBe('true')
    await w.get('[data-testid="feed-network-reddit"]').trigger('click')
    expect(w.emitted('update:network')?.[0]).toEqual(['reddit'])
    await w.get('[data-testid="feed-filter-persona"]').setValue('0')
    expect(w.emitted('update:persona')?.[0]).toEqual(['0'])
    await w.get('[data-testid="feed-filter-round"]').setValue('2')
    expect(w.emitted('update:round')?.[0]).toEqual([2])
    await w.get('[data-testid="feed-filter-query"]').setValue('Abgabe')
    expect(w.emitted('update:query')?.[0]).toEqual(['Abgabe'])
  })

  it('zeigt die Streitfrage als Text ohne Filterelement; Reset nur bei aktiven Filtern', async () => {
    const w = mount(FeedSidebar, { props, global })
    expect(w.get('[data-testid="feed-contested"]').text()).toContain('Soll es eine Abgabe geben?')
    expect(w.get('[data-testid="feed-contested"]').find('select, input, button').exists()).toBe(false)
    expect(w.find('[data-testid="feed-filter-reset"]').exists()).toBe(false)
    await w.setProps({ query: 'x' })
    await w.get('[data-testid="feed-filter-reset"]').trigger('click')
    expect(w.emitted('reset')).toHaveLength(1)
  })

  it('nennt eine fehlende Streitfrage', () => {
    const w = mount(FeedSidebar, { props: { ...props, contestedQuestion: null }, global })
    expect(w.get('[data-testid="feed-contested"]').text()).toContain('keine Streitfrage erfasst')
  })
})

describe('FeedNotices', () => {
  const base = { error: null, truncated: false, limit: 5000, invalidCount: 0, evictedCount: 0, unroundedCount: 0, streamError: false }

  it('zeigt ohne Anlass nichts', () => {
    const w = mount(FeedNotices, { props: base, global })
    expect(w.findAll('p')).toHaveLength(0)
  })

  it('zeigt jeden Zustand sichtbar; Fehler als alert mit Erneut laden', async () => {
    const w = mount(FeedNotices, {
      props: { error: 'twitter: 500', truncated: true, limit: 5000, invalidCount: 2, evictedCount: 7, unroundedCount: 4, streamError: true },
      global,
    })
    const err = w.get('[data-testid="notice-error"]')
    expect(err.attributes('role')).toBe('alert')
    expect(err.text()).toContain('twitter: 500')
    await w.get('[data-testid="notice-retry"]').trigger('click')
    expect(w.emitted('reload')).toHaveLength(1)
    expect(w.get('[data-testid="notice-truncated"]').text()).toBe('Es werden nur die neuesten 5000 Beiträge je Netzwerk gezeigt.')
    expect(w.get('[data-testid="notice-invalid"]').text()).toContain('2 Beiträge')
    expect(w.get('[data-testid="notice-evicted"]').text()).toContain('7 ältere Beiträge')
    expect(w.get('[data-testid="notice-unrounded"]').text()).toBe('4 Beiträge ohne Rundenangabe werden in jeder Runde gezeigt.')
    expect(w.get('[data-testid="notice-stream"]').text()).toContain('Live-Verbindung')
  })
})

describe('PersonaCard', () => {
  const persona = {
    personaId: '0', name: 'Anna', username: null, role: 'Ärztin', bio: 'Arbeitet in Köln.', stance: null, contestedQuestion: null,
  }

  it('zeigt „Haltung nicht erfasst", wenn stance null ist, und rät nicht', () => {
    const w = mount(PersonaCard, { props: { persona }, global })
    expect(w.get('[data-testid="persona-card-stance"]').text()).toBe('Haltung nicht erfasst')
    expect(w.get('[data-testid="persona-card-role"]').text()).toBe('Ärztin')
    expect(w.get('[data-testid="persona-card-bio"]').text()).toBe('Arbeitet in Köln.')
    expect(w.text()).not.toContain('Befragen')
  })

  it('zeigt die Haltung, wenn erfasst', () => {
    const w = mount(PersonaCard, { props: { persona: { ...persona, stance: 'skeptisch' } }, global })
    expect(w.get('[data-testid="persona-card-stance"]').text()).toBe('skeptisch')
  })

  it('unterscheidet fehlendes Profil und keine Auswahl', () => {
    const missing = mount(PersonaCard, { props: { persona: null, fallbackName: 'Carl' }, global })
    expect(missing.get('[data-testid="persona-card-missing"]').text()).toContain('kein Profil')
    const none = mount(PersonaCard, { props: { persona: null }, global })
    expect(none.find('[data-testid="persona-card-none"]').exists()).toBe(true)
  })
})

describe('RoundPanel', () => {
  it('zeigt Runde x von y mit Aktivität', () => {
    const w = mount(RoundPanel, { props: { round: 11, total: 24, twitter: 5, reddit: 2 }, global })
    expect(w.get('[data-testid="round-panel-title"]').text()).toBe('Runde 11 von 24')
    expect(w.get('[data-testid="round-panel-activity"]').text()).toBe('5 Twitter · 2 Reddit')
  })

  it('nennt unbekannte Gesamtzahl, leere Runde und fehlende Rundenangabe', async () => {
    const w = mount(RoundPanel, { props: { round: 3, total: null, twitter: 0, reddit: 0 }, global })
    expect(w.get('[data-testid="round-panel-title"]').text()).toBe('Runde 3 von ?')
    expect(w.get('[data-testid="round-panel-activity"]').text()).toBe('Keine Beiträge in dieser Runde.')
    await w.setProps({ round: null })
    expect(w.get('[data-testid="round-panel-title"]').text()).toBe('Noch keine Rundenangabe')
  })
})
