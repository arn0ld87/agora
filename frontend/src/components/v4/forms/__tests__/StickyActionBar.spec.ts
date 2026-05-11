import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import StickyActionBar from '../StickyActionBar.vue'

describe('StickyActionBar', () => {
  it('renders left and right slots', () => {
    const w = mount(StickyActionBar, {
      slots: {
        left: '<button class="add-btn">+ Override</button>',
        right: '<button class="save-btn">Speichern</button>',
      },
    })
    expect(w.find('.add-btn').exists()).toBe(true)
    expect(w.find('.save-btn').exists()).toBe(true)
  })

  it('shows dirty hint when dirty=true', () => {
    const w = mount(StickyActionBar, {
      props: { dirty: true },
    })
    expect(w.find('.v4-sticky-bar__dirty-hint').text()).toContain('Ungespeicherte')
  })

  it('hides dirty hint when dirty=false', () => {
    const w = mount(StickyActionBar, {
      props: { dirty: false },
    })
    expect(w.find('.v4-sticky-bar__dirty-hint').exists()).toBe(false)
  })

  it('has sticky-bar class', () => {
    const w = mount(StickyActionBar)
    expect(w.find('.v4-sticky-bar').exists()).toBe(true)
  })
})
