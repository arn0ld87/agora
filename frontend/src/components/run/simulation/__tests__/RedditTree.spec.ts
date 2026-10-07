import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import RedditTree from '../RedditTree.vue'
import { buildRedditTree } from '@/composables/run/simulation/threads'
import { i18n, makePost, makeRouter } from './fixtures'

const root = makePost({ post_id: 'reddit:1', platform: 'reddit' })
const c1 = makePost({ post_id: 'reddit:comment:2', platform: 'reddit', kind: 'comment', parent_post_id: 'reddit:1', root_post_id: 'reddit:1', persona_name: 'Berta', timestamp: '2026-10-01T10:01:00+00:00' })
const c2 = makePost({ post_id: 'reddit:comment:3', platform: 'reddit', kind: 'comment', parent_comment_id: 'reddit:comment:2', parent_post_id: 'reddit:comment:2', root_post_id: 'reddit:1', timestamp: '2026-10-01T10:02:00+00:00' })

function mountTree(claimId: string | null = null) {
  const result = buildRedditTree('reddit:1', [root, c1, c2])
  return mount(RedditTree, {
    props: { nodes: result.tree, claimId },
    global: { plugins: [makeRouter(), i18n] },
  })
}

describe('RedditTree', () => {
  it('zeigt Kommentare verschachtelt, je Kommentar mit SIM-Kennzeichen', () => {
    const w = mountTree()
    const nodes = w.findAll('[data-testid="reddit-node"]')
    expect(nodes.map((n) => n.attributes('data-depth'))).toEqual(['1', '2'])
    expect(w.findAll('[data-testid="post-sim"]')).toHaveLength(2)
  })

  it('klappt einen Ast per Knopf mit aria-expanded ein und aus', async () => {
    const w = mountTree()
    const toggle = w.get('[data-testid="reddit-toggle"]')
    expect(toggle.element.tagName).toBe('BUTTON')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    const panel = w.get(`#${toggle.attributes('aria-controls')}`)
    expect((panel.element as HTMLElement).style.display).not.toBe('none')

    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect((panel.element as HTMLElement).style.display).toBe('none')
    expect(toggle.text()).toContain('ausklappen')
    expect(toggle.text()).toContain('1 Antworten')

    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(toggle.text()).toContain('einklappen')
  })

  it('hat nur an Kommentaren mit Antworten einen Knopf', () => {
    const w = mountTree()
    expect(w.findAll('[data-testid="reddit-toggle"]')).toHaveLength(1)
  })

  it('hebt den Beitrag aus ?claim= hervor', () => {
    const w = mountTree('reddit:comment:3')
    const marked = w.findAll('[aria-current="true"]')
    expect(marked).toHaveLength(1)
    expect(marked[0].text()).toContain('Text reddit:comment:3')
  })
})
