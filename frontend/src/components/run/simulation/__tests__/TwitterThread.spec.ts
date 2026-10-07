import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TwitterThread from '../TwitterThread.vue'
import { buildTwitterThread } from '@/composables/run/simulation/threads'
import { i18n, makePost, makeRouter } from './fixtures'

const toFor = (postId: string) => ({ name: 'RunSimulationPost', params: { simulationId: 'sim_1', postId } })

function mountThread(rootId: string, posts: ReturnType<typeof makePost>[], claimId: string | null = null) {
  return mount(TwitterThread, {
    props: { result: buildTwitterThread(rootId, posts), claimId, toFor },
    global: { plugins: [makeRouter(), i18n] },
  })
}

const root = makePost({ post_id: 'twitter:1', timestamp: '2026-10-01T10:00:00+00:00' })
const r1 = makePost({ post_id: 'twitter:2', kind: 'comment', parent_post_id: 'twitter:1', root_post_id: 'twitter:1', timestamp: '2026-10-01T10:01:00+00:00' })
const r2 = makePost({ post_id: 'twitter:3', kind: 'comment', parent_post_id: 'twitter:2', root_post_id: 'twitter:1', timestamp: '2026-10-01T10:02:00+00:00' })
const r3 = makePost({ post_id: 'twitter:4', kind: 'comment', parent_post_id: 'twitter:1', root_post_id: 'twitter:1', timestamp: '2026-10-01T10:03:00+00:00' })

describe('TwitterThread', () => {
  it('zeigt den Beitrag oben und die Antworten mit Tiefe und Ende der Verbindungslinie', () => {
    const w = mountThread('twitter:1', [root, r1, r2, r3])
    expect(w.get('[data-testid="thread-root"]').text()).toContain('Text twitter:1')
    const nodes = w.findAll('[data-testid="thread-node"]')
    expect(nodes.map((n) => n.attributes('data-depth'))).toEqual(['1', '2', '1'])
    expect(nodes.map((n) => n.attributes('data-last'))).toEqual(['false', 'true', 'true'])
    expect(nodes[0].attributes('style')).toContain('--depth: 1')
    expect(nodes[1].attributes('style')).toContain('--depth: 2')
  })

  it('markiert nur die letzte Antwort einer Ebene als Ende', () => {
    const w = mountThread('twitter:1', [root, r1, r3])
    const nodes = w.findAll('[data-testid="thread-node"]')
    expect(nodes.map((n) => n.attributes('data-last'))).toEqual(['false', 'true'])
    expect(nodes[1].classes()).toContain('thread__node--last')
  })

  it('führt Zitate und Reposts auf', () => {
    const quote = makePost({ post_id: 'twitter:5', kind: 'quote', quoted_post_id: 'twitter:1', body: 'Zitat-Text' })
    const repost = makePost({ post_id: 'twitter:6', kind: 'repost', reposted_post_id: 'twitter:1', body: '' })
    const w = mountThread('twitter:1', [root, quote, repost])
    expect(w.get('[data-testid="thread-quotes"]').text()).toContain('Zitat-Text')
    expect(w.get('[data-testid="thread-quotes"] a').attributes('href')).toContain('/post/twitter:5')
    expect(w.get('[data-testid="thread-reposts"]').text()).toBe('Weiterleitungen: 1')
  })

  it('meldet eine fehlende Wurzel und zeigt die Antworten trotzdem', () => {
    const w = mountThread('twitter:2', [r1, r2])
    expect(w.get('[data-testid="thread-root-missing"]').text()).toContain('außerhalb des geladenen Ausschnitts')
    expect(w.find('[data-testid="thread-root"]').exists()).toBe(false)
    expect(w.findAll('[data-testid="thread-node"]').length).toBeGreaterThan(0)
  })

  it('meldet eine fehlerhafte Kette als Fehler', () => {
    const a = makePost({ post_id: 'twitter:a', kind: 'comment', parent_post_id: 'twitter:b' })
    const b = makePost({ post_id: 'twitter:b', kind: 'comment', parent_post_id: 'twitter:a' })
    const w = mountThread('twitter:a', [a, b])
    expect(w.get('[data-testid="thread-broken"]').attributes('role')).toBe('alert')
    expect(w.find('[data-testid="thread-node"]').exists()).toBe(false)
  })

  it('hebt den Beitrag aus ?claim= hervor', () => {
    const w = mountThread('twitter:1', [root, r1], 'twitter:2')
    const marked = w.findAll('[aria-current="true"]')
    expect(marked).toHaveLength(1)
    expect(marked[0].text()).toContain('Text twitter:2')
    expect(w.text()).toContain('Beleg dieser Aussage')
  })
})
