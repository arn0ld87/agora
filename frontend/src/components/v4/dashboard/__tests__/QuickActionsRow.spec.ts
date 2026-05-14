import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import QuickActionsRow from '../QuickActionsRow.vue'
import { makeI18n, makeRouter } from './dashTestHelpers'

describe('QuickActionsRow', () => {
  it('rendert drei RouterLink-Tiles', async () => {
    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(QuickActionsRow, {
      global: { plugins: [makeI18n(), router] },
    })
    const tiles = w.findAll('.qa-tile')
    expect(tiles).toHaveLength(3)
    const labels = tiles.map(t => t.find('.qa-tile__label').text())
    expect(labels).toEqual(['Vergleichen', 'Historie', 'Einstellungen'])
  })

  it('hat Hinweise unter jedem Label', async () => {
    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(QuickActionsRow, {
      global: { plugins: [makeI18n(), router] },
    })
    const hints = w.findAll('.qa-tile__hint')
    expect(hints).toHaveLength(3)
    expect(hints[2].text()).toContain('LLM')
  })
})
