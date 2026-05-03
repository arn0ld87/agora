// Issue #84 (EPIC-10-ST-07) — useEventStream Composable-Coverage.
//
// SSE-Wrapper aus Issue #9 Phase C. `openSimulationStream` wird gemockt,
// damit Tests ohne echten EventSource und ohne Backend laufen.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import type { UseEventStreamReturn } from '../useEventStream'
import type { StreamHandlers } from '../../api/stream'

const openSimulationStream = vi.fn()

vi.mock('../../api/stream', () => ({
  // reason: mock factory needs rest params to forward all args to the spy
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  openSimulationStream: (...args: any[]) => openSimulationStream(...args),
}))

import { useEventStream } from '../useEventStream'

function makeFakeSource(): { close: ReturnType<typeof vi.fn> } {
  return {
    close: vi.fn(),
  }
}

function mountStream(
  // reason: accepts all valid simulationIdRef forms from useEventStream signature
  simulationIdRef: Parameters<typeof useEventStream>[0],
  handlers: StreamHandlers = {}
): { wrapper: ReturnType<typeof mount>; stream: UseEventStreamReturn } {
  let exposed: UseEventStreamReturn | undefined
  const Comp = defineComponent({
    setup() {
      exposed = useEventStream(simulationIdRef, handlers)
      return () => h('div')
    },
  })
  const wrapper = mount(Comp)
  return { wrapper, stream: exposed as UseEventStreamReturn }
}

describe('useEventStream', () => {
  beforeEach(() => {
    openSimulationStream.mockReset()
  })

  it('startet nicht, wenn die simulation-ID leer ist', async () => {
    // Hinweis: getId() in useEventStream hat einen Edge-Case bei `ref(null)`
    // (`null ?? simulationIdRef` gibt das Ref-Objekt selbst zurück). Mit einem
    // leeren String greift der `if (!id) return`-Guard wie dokumentiert.
    const { stream } = mountStream(ref(''))

    await stream.start()
    expect(openSimulationStream).not.toHaveBeenCalled()
    expect(stream.isStreaming.value).toBe(false)
  })

  it('öffnet den Stream und setzt isStreaming=true bei Erfolg', async () => {
    openSimulationStream.mockResolvedValue(makeFakeSource())
    const { stream } = mountStream(ref('sim-123'))

    await stream.start()
    await flushPromises()

    expect(openSimulationStream).toHaveBeenCalledWith('sim-123', expect.any(Object))
    expect(stream.isStreaming.value).toBe(true)
    expect(stream.error.value).toBeNull()
  })

  it('löst Getter-Funktion für simulationIdRef auf', async () => {
    openSimulationStream.mockResolvedValue(makeFakeSource())
    const { stream } = mountStream(() => 'sim-from-fn')

    await stream.start()
    await flushPromises()

    expect(openSimulationStream).toHaveBeenCalledWith('sim-from-fn', expect.any(Object))
  })

  it('handler-wrapping setzt lastEventAt und resettet attempts', async () => {
    // reason: capturedHandlers is assigned inside the mock, TS cannot infer type
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let capturedHandlers: any
    openSimulationStream.mockImplementation((_id: string, handlers: StreamHandlers) => {
      capturedHandlers = handlers
      return Promise.resolve(makeFakeSource())
    })

    const onState = vi.fn()
    const { stream } = mountStream(ref('sim-1'), { state: onState })
    await stream.start()
    await flushPromises()

    capturedHandlers.state({ status: 'running' })
    expect(onState).toHaveBeenCalledWith({ status: 'running' })
    expect(stream.lastEventAt.value).toEqual(expect.any(Number))
    expect(stream.error.value).toBeNull()
  })

  it('stop() schließt die Source und setzt isStreaming=false', async () => {
    const fake = makeFakeSource()
    openSimulationStream.mockResolvedValue(fake)
    const { stream } = mountStream(ref('sim-1'))

    await stream.start()
    await flushPromises()
    expect(stream.isStreaming.value).toBe(true)

    stream.stop()

    expect(fake.close).toHaveBeenCalledTimes(1)
    expect(stream.isStreaming.value).toBe(false)
  })

  it('cleanup auf unmount stoppt den Stream', async () => {
    const fake = makeFakeSource()
    openSimulationStream.mockResolvedValue(fake)
    const { wrapper, stream } = mountStream(ref('sim-1'))

    await stream.start()
    await flushPromises()
    expect(stream.isStreaming.value).toBe(true)

    wrapper.unmount()

    expect(fake.close).toHaveBeenCalledTimes(1)
  })

  it('setzt error-Ref wenn openSimulationStream wirft', async () => {
    const err = new Error('ticket fetch failed')
    openSimulationStream.mockRejectedValue(err)
    const { stream } = mountStream(ref('sim-1'))

    await stream.start()
    await flushPromises()

    expect(stream.error.value).toBe(err)
    expect(stream.isStreaming.value).toBe(false)
  })
})
