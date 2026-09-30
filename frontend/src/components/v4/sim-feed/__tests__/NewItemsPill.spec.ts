/**
 * NewItemsPill — Slice UI-2b (#1713), docs/design/simulation-feed.md §2.6.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

import NewItemsPill from '../NewItemsPill.vue'

describe('NewItemsPill', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('visible=false rendert keinen Button', () => {
    const w = mount(NewItemsPill, { props: { count: 3, visible: false } })
    expect(w.find('button').exists()).toBe(false)
  })

  it('count=0 rendert keinen Button, auch wenn visible=true', () => {
    const w = mount(NewItemsPill, { props: { count: 0, visible: true } })
    expect(w.find('button').exists()).toBe(false)
  })

  it('visible=true und count>0 rendert den Button mit Zaehler-Key', () => {
    const w = mount(NewItemsPill, { props: { count: 5, visible: true } })
    expect(w.get('button').text()).toBe('feed.newItems')
  })

  it('Klick emittiert click', async () => {
    const w = mount(NewItemsPill, { props: { count: 5, visible: true } })
    await w.get('button').trigger('click')
    expect(w.emitted('click')).toHaveLength(1)
  })

  it('emittiert dismiss statt click nach 20s Inaktivitaet', async () => {
    const w = mount(NewItemsPill, { props: { count: 2, visible: true } })
    vi.advanceTimersByTime(20_000)
    await Promise.resolve()
    expect(w.emitted('dismiss')).toHaveLength(1)
    expect(w.emitted('click')).toBeUndefined()
  })
})
