/**
 * EmptyState — Tests
 * Slice D · 2026-05-11
 *
 * Test 1: Mount mit Default-Props
 * Test 2: Custom title + subtitle
 * Test 3: actions-Slot wird gerendert
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import EmptyState from '../EmptyState.vue'

describe('EmptyState', () => {
  it('Test 1: Mount mit Default-Props — zeigt Default-Title + Icon', () => {
    const wrapper = mount(EmptyState)

    expect(wrapper.find('.es-title').text()).toBe('Keine Daten')
    // Default-SVG vorhanden
    expect(wrapper.find('svg').exists()).toBe(true)
    // Kein Subtitle
    expect(wrapper.find('.es-subtitle').exists()).toBe(false)
  })

  it('Test 2: Custom title + subtitle werden angezeigt', () => {
    const wrapper = mount(EmptyState, {
      props: {
        title: 'Noch keine Dokumente',
        subtitle: 'Lade ein Dataset hoch, um zu beginnen.',
      },
    })

    expect(wrapper.find('.es-title').text()).toBe('Noch keine Dokumente')
    expect(wrapper.find('.es-subtitle').exists()).toBe(true)
    expect(wrapper.find('.es-subtitle').text()).toBe('Lade ein Dataset hoch, um zu beginnen.')
  })

  it('Test 3: actions-Slot wird korrekt gerendert', () => {
    const wrapper = mount(EmptyState, {
      props: { title: 'Leer' },
      slots: {
        actions: '<button data-testid="upload-btn">Hochladen</button>',
      },
    })

    expect(wrapper.find('.es-actions').exists()).toBe(true)
    const btn = wrapper.find('[data-testid="upload-btn"]')
    expect(btn.exists()).toBe(true)
    expect(btn.text()).toBe('Hochladen')
  })

  it('Test 3b: ohne actions-Slot kein es-actions-Container', () => {
    const wrapper = mount(EmptyState, {
      props: { title: 'Leer' },
    })
    expect(wrapper.find('.es-actions').exists()).toBe(false)
  })
})
