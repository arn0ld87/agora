
import { describe, it, expect } from 'vitest'
import SidebarGroup from '../../components/v4/shell/SidebarGroup.vue'
describe('diag', () => {
  it('what is SidebarGroup', () => {
    const t = typeof SidebarGroup
    expect(['object', 'function']).toContain(t)
  })
})
