/**
 * SimActionsTable — Slice UI-2b (#1713), docs/design/simulation-feed.md §2.10.
 * Deckt loading(initial|append)/empty-Zustaende, Spaltenwerte,
 * role_conflict-/success=false-Chips, loadMore- und openPost-Events ab.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { SimActionPage, SimActionRecord } from '@/contracts/simActionContract'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

import SimActionsTable from '../SimActionsTable.vue'

function mkRecord(overrides: Partial<SimActionRecord> = {}): SimActionRecord {
  return {
    round_num: 0,
    timestamp: '2026-05-15T12:00:00Z',
    platform: 'reddit',
    agent_id: 'alice',
    agent_name: 'Alice',
    action_type: 'CREATE_POST',
    content: 'Hallo Welt',
    success: true,
    sim_time: null,
    role_conflict: null,
    target_post_id: null,
    target_comment_id: null,
    target_agent_id: null,
    target_agent_name: null,
    ...overrides,
  }
}

function mkPage(items: SimActionRecord[] = [], nextCursor: string | null = null): SimActionPage {
  return { items, next_cursor: nextCursor }
}

describe('SimActionsTable', () => {
  it('initiales Laden (keine Items) zeigt Skeleton mit aria-busy', () => {
    const w = mount(SimActionsTable, {
      props: { page: mkPage(), loading: true, filters: {} },
    })
    expect(w.find('[aria-busy="true"]').exists()).toBe(true)
    expect(w.find('table').exists()).toBe(false)
  })

  it('leere Liste ohne Laden zeigt den Empty-State', () => {
    const w = mount(SimActionsTable, {
      props: { page: mkPage(), loading: false, filters: {} },
    })
    expect(w.get('[role="status"]').text()).toBe('feed.actionsTable.empty')
  })

  it('rendert Spaltenwerte aus dem Vertrag (agent_name, content, platform)', () => {
    const page = mkPage([mkRecord({ agent_name: 'Bob', content: 'Testinhalt' })])
    const w = mount(SimActionsTable, { props: { page, loading: false, filters: {} } })
    expect(w.text()).toContain('Bob')
    expect(w.text()).toContain('Testinhalt')
  })

  it('leerer target_post_id zeigt den noTarget-Platzhalter statt eines leeren Feldes', () => {
    const page = mkPage([mkRecord({ target_post_id: null })])
    const w = mount(SimActionsTable, { props: { page, loading: false, filters: {} } })
    expect(w.text()).toContain('feed.actionsTable.noTarget')
  })

  it('role_conflict zeigt den Rollenkonflikt-Chip (Degradation sichtbar)', () => {
    const page = mkPage([mkRecord({ role_conflict: 'foreign_role' })])
    const w = mount(SimActionsTable, { props: { page, loading: false, filters: {} } })
    expect(w.find('.sat-badge--warn').exists()).toBe(true)
  })

  it('success=false zeigt den fehlgeschlagen-Chip statt die Zeile stillschweigend normal zu zeigen', () => {
    const page = mkPage([mkRecord({ success: false })])
    const w = mount(SimActionsTable, { props: { page, loading: false, filters: {} } })
    expect(w.find('.sat-badge--danger').exists()).toBe(true)
    expect(w.get('.sat-row').classes()).toContain('sat-row--failed')
  })

  it('Zeile mit target_post_id ist per Klick und Enter aktivierbar (openPost)', async () => {
    const page = mkPage([mkRecord({ target_post_id: 'p-1' })])
    const w = mount(SimActionsTable, { props: { page, loading: false, filters: {} } })
    const row = w.get('.sat-row')
    expect(row.attributes('tabindex')).toBe('0')
    await row.trigger('click')
    expect(w.emitted('openPost')?.[0]).toEqual(['p-1'])
    await row.trigger('keydown', { key: 'Enter' })
    expect(w.emitted('openPost')?.[1]).toEqual(['p-1'])
  })

  it('Zeile ohne target_post_id ist nicht fokussierbar und emittiert nichts', async () => {
    const page = mkPage([mkRecord({ target_post_id: null })])
    const w = mount(SimActionsTable, { props: { page, loading: false, filters: {} } })
    const row = w.get('.sat-row')
    expect(row.attributes('tabindex')).toBeUndefined()
    await row.trigger('click')
    expect(w.emitted('openPost')).toBeUndefined()
  })

  it('next_cursor gesetzt zeigt den "Weitere laden"-Button, der loadMore emittiert', async () => {
    const page = mkPage([mkRecord()], 'cursor-2')
    const w = mount(SimActionsTable, { props: { page, loading: false, filters: {} } })
    await w.get('.sat-load-more').trigger('click')
    expect(w.emitted('loadMore')).toHaveLength(1)
  })

  it('next_cursor=null verbirgt den "Weitere laden"-Button', () => {
    const page = mkPage([mkRecord()], null)
    const w = mount(SimActionsTable, { props: { page, loading: false, filters: {} } })
    expect(w.find('.sat-load-more').exists()).toBe(false)
  })

  it('loading=true mit bereits vorhandenen Items zeigt ein Append-Skeleton statt den Button', () => {
    const page = mkPage([mkRecord()], 'cursor-2')
    const w = mount(SimActionsTable, { props: { page, loading: true, filters: {} } })
    expect(w.find('.sat-skeleton--append').exists()).toBe(true)
    expect(w.find('.sat-load-more').exists()).toBe(false)
    expect(w.find('table').exists()).toBe(true)
  })
})
