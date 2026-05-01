// Issue #84 (EPIC-10-ST-07) — useWorkspaceStatus Composable-Coverage.
//
// Map-driven status aggregation aus EPIC-03 ST-02. useI18n() wird gemockt,
// damit Tests ohne i18n-Setup laufen.

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key) => `t:${key}`,
  }),
}))

import { useWorkspaceStatus } from '../useWorkspaceStatus'

function mountStatus(args) {
  let exposed
  const Comp = defineComponent({
    setup() {
      exposed = useWorkspaceStatus(args)
      return () => h('div')
    },
  })
  const wrapper = mount(Comp)
  return { wrapper, status: exposed }
}

describe('useWorkspaceStatus', () => {
  it('initial-Status wird als currentStatus übernommen', () => {
    const { status } = mountStatus({
      initial: 'completed',
      map: { completed: { kind: 'done', text: 'common.completed' } },
    })

    expect(status.currentStatus.value).toBe('completed')
    expect(status.statusKind.value).toBe('done')
    expect(status.statusText.value).toBe('t:common.completed')
  })

  it('updateStatus() ändert currentStatus und triggert die Computeds', async () => {
    const { status } = mountStatus({
      initial: 'processing',
      map: {
        processing: { kind: 'running', text: 'common.processing' },
        completed: { kind: 'done', text: 'common.completed' },
      },
    })

    expect(status.statusKind.value).toBe('running')

    status.updateStatus('completed')
    expect(status.currentStatus.value).toBe('completed')
    expect(status.statusKind.value).toBe('done')
    expect(status.statusText.value).toBe('t:common.completed')
  })

  it('greift auf `fallback` zurück wenn der Status nicht in der Map ist', () => {
    const { status } = mountStatus({
      initial: 'unknown_state',
      map: { processing: { kind: 'running', text: 'common.processing' } },
      fallback: { kind: 'idle', text: 'common.idle' },
    })

    expect(status.statusKind.value).toBe('idle')
    expect(status.statusText.value).toBe('t:common.idle')
  })

  it('nutzt DEFAULT_FALLBACK ohne expliziten fallback-arg', () => {
    const { status } = mountStatus({
      initial: 'mystery',
      map: {},
    })

    expect(status.statusKind.value).toBe('running')
    expect(status.statusText.value).toBe('t:common.processing')
  })

  it('arbeitet ohne Argumente (alle Defaults)', () => {
    const { status } = mountStatus()

    expect(status.currentStatus.value).toBe('processing')
    expect(status.statusKind.value).toBe('running')
    expect(status.statusText.value).toBe('t:common.processing')
  })

  it('mehrfaches updateStatus mit gleichem Wert ist idempotent', () => {
    const { status } = mountStatus({
      initial: 'processing',
      map: { processing: { kind: 'running', text: 'common.processing' } },
    })

    status.updateStatus('processing')
    status.updateStatus('processing')

    expect(status.currentStatus.value).toBe('processing')
    expect(status.statusKind.value).toBe('running')
  })
})
