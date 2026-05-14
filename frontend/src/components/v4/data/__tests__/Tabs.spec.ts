/**
 * Tabs — Tests
 * Slice D · 2026-05-11
 *
 * Test 1: Active Tab basierend auf modelValue
 * Test 2: Click emittiert update:modelValue
 * Test 3: URL-Sync via vue-router (mock)
 * Test 4: Disabled-Tab nicht clickbar
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import Tabs from '../Tabs.vue'
import type { TabItem } from '../Tabs.vue'

const tabs: TabItem[] = [
  { key: 'overview', label: 'Übersicht' },
  { key: 'settings', label: 'Einstellungen', badge: 3 },
  { key: 'logs', label: 'Logs', disabled: true },
]

async function makeRouter(query: Record<string, string> = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div/>' } }],
  })
  const loc = Object.keys(query).length > 0 ? { path: '/', query } : '/'
  await router.push(loc)
  return router
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('Tabs', () => {
  it('Test 1: Active Tab basierend auf modelValue', async () => {
    const router = await makeRouter()

    const wrapper = mount(Tabs, {
      props: { modelValue: 'settings', tabs },
      global: { plugins: [router] },
    })

    const buttons = wrapper.findAll('[role="tab"]')
    expect(buttons).toHaveLength(3)

    // settings-Tab aktiv
    expect(buttons[1].classes()).toContain('tabs-item--active')
    expect(buttons[1].attributes('aria-selected')).toBe('true')

    // overview nicht aktiv
    expect(buttons[0].classes()).not.toContain('tabs-item--active')
    expect(buttons[0].attributes('aria-selected')).toBe('false')
  })

  it('Test 1b: Badge wird neben Label gerendert', async () => {
    const router = await makeRouter()

    const wrapper = mount(Tabs, {
      props: { modelValue: 'overview', tabs },
      global: { plugins: [router] },
    })

    // settings-Tab hat Badge 3
    const badge = wrapper.find('.tabs-badge')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toBe('3')
  })

  it('Test 2: Click emittiert update:modelValue', async () => {
    const router = await makeRouter()

    const wrapper = mount(Tabs, {
      props: { modelValue: 'settings', tabs },
      global: { plugins: [router] },
    })

    // Click auf 'overview'
    const overviewBtn = wrapper.findAll('[role="tab"]')[0]
    await overviewBtn.trigger('click')

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeDefined()
    expect(emitted![0]).toEqual(['overview'])
  })

  it('Test 3: URL-Sync schreibt Query-Param wenn modelValue sich ändert', async () => {
    const router = await makeRouter()
    const replaceSpy = vi.spyOn(router, 'replace')

    const wrapper = mount(Tabs, {
      props: { modelValue: 'overview', tabs, urlSync: true },
      global: { plugins: [router] },
    })

    // modelValue ändern
    await wrapper.setProps({ modelValue: 'settings' })

    expect(replaceSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        query: expect.objectContaining({ tab: 'settings' }),
      }),
    )
  })

  it('Test 3b: urlSync=false → kein router.replace-Aufruf', async () => {
    const router = await makeRouter()
    const replaceSpy = vi.spyOn(router, 'replace')

    const wrapper = mount(Tabs, {
      props: { modelValue: 'overview', tabs, urlSync: false },
      global: { plugins: [router] },
    })

    await wrapper.setProps({ modelValue: 'settings' })

    expect(replaceSpy).not.toHaveBeenCalled()
  })

  it('Test 4: Disabled-Tab nicht clickbar — emittiert kein Event', async () => {
    const router = await makeRouter()

    const wrapper = mount(Tabs, {
      props: { modelValue: 'overview', tabs },
      global: { plugins: [router] },
    })

    // logs-Tab ist disabled
    const logsBtn = wrapper.findAll('[role="tab"]')[2]
    expect(logsBtn.classes()).toContain('tabs-item--disabled')
    expect(logsBtn.attributes('aria-disabled')).toBe('true')

    await logsBtn.trigger('click')

    // Kein Emit
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })
})
