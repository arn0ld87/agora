// Issue #84 (EPIC-10-ST-07) — usePolling Composable-Coverage.
//
// Lifecycle-Vertrag: start/stop/tick + onUnmounted-Cleanup. Wir mounten ein
// Dummy-Setup, das `usePolling` aufruft, und testen Verhalten via fake-timers.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

import { usePolling } from '../usePolling'

function mountPolling(task, intervalMs, options) {
  let exposed
  const Comp = defineComponent({
    setup() {
      exposed = usePolling(task, intervalMs, options)
      return () => h('div')
    },
  })
  const wrapper = mount(Comp)
  return { wrapper, polling: exposed }
}

describe('usePolling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('startet den Timer und ruft `task` periodisch auf', async () => {
    const task = vi.fn().mockResolvedValue()
    const { polling } = mountPolling(task, 1000)

    await polling.start()
    expect(task).toHaveBeenCalledTimes(0) // ohne immediate kein erster Call

    await vi.advanceTimersByTimeAsync(1000)
    expect(task).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(1000)
    expect(task).toHaveBeenCalledTimes(2)

    polling.stop()
  })

  it('führt `task` sofort aus wenn `immediate: true`', async () => {
    const task = vi.fn().mockResolvedValue()
    const { polling } = mountPolling(task, 1000, { immediate: true })

    await polling.start()
    await flushPromises()
    expect(task).toHaveBeenCalledTimes(1)

    polling.stop()
  })

  it('stoppt nach `stop()` und ruft `task` nicht mehr', async () => {
    const task = vi.fn().mockResolvedValue()
    const { polling } = mountPolling(task, 500)

    await polling.start()
    await vi.advanceTimersByTimeAsync(500)
    expect(task).toHaveBeenCalledTimes(1)

    polling.stop()
    expect(polling.isRunning.value).toBe(false)

    await vi.advanceTimersByTimeAsync(2000)
    expect(task).toHaveBeenCalledTimes(1)
  })

  it('cleanup auf unmount stoppt den Timer', async () => {
    const task = vi.fn().mockResolvedValue()
    const { wrapper, polling } = mountPolling(task, 500)

    await polling.start()
    await vi.advanceTimersByTimeAsync(500)
    expect(task).toHaveBeenCalledTimes(1)

    wrapper.unmount()

    await vi.advanceTimersByTimeAsync(2000)
    expect(task).toHaveBeenCalledTimes(1)
  })

  it('ruft `onError` bei task-Fehler statt zu werfen', async () => {
    const err = new Error('boom')
    const task = vi.fn().mockRejectedValue(err)
    const onError = vi.fn()
    const { polling } = mountPolling(task, 500, { onError })

    await polling.start({ immediate: true })
    await flushPromises()

    expect(task).toHaveBeenCalledTimes(1)
    expect(onError).toHaveBeenCalledWith(err)

    polling.stop()
  })

  it('mehrfacher start() startet keinen zweiten Timer', async () => {
    const task = vi.fn().mockResolvedValue()
    const { polling } = mountPolling(task, 1000)

    await polling.start()
    await polling.start() // No-op
    await polling.start()

    await vi.advanceTimersByTimeAsync(1000)
    expect(task).toHaveBeenCalledTimes(1) // nur ein Tick pro Intervall

    polling.stop()
  })

  it('isTicking schützt vor concurrent ticks', async () => {
    let resolveTask
    const task = vi.fn().mockImplementation(() => new Promise((resolve) => {
      resolveTask = resolve
    }))
    const { polling } = mountPolling(task, 100)

    await polling.start()

    await vi.advanceTimersByTimeAsync(100)
    expect(task).toHaveBeenCalledTimes(1)
    expect(polling.isTicking.value).toBe(true)

    // Während task hängt, sollten weitere Intervall-Ticks NICHT noch einen Call machen
    await vi.advanceTimersByTimeAsync(300)
    expect(task).toHaveBeenCalledTimes(1)

    resolveTask()
    await flushPromises()
    expect(polling.isTicking.value).toBe(false)

    polling.stop()
  })
})
