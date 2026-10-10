import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AxiosAdapter } from 'axios'
import service from '@/api'
import GraphCanvas from '../GraphCanvas.vue'
import GraphReader from '@/components/graph-library/GraphReader.vue'
import { buildReaderModel } from '@/composables/graph-library/graphReaderModel'
import { CanvasStub, graphFixture, makeI18n, makeRouter } from '@/components/graph-library/__tests__/fixtures'

vi.mock('@/composables/useGraphRender', () => ({
  useGraphRender: () => ({
    selectedItem: ref(null),
    render: vi.fn(),
    isPaused: ref(false),
    togglePause: vi.fn(),
    resetLayout: vi.fn(),
    minimapNodes: ref([]),
    minimapViewport: ref({ x: 0, y: 0, k: 1, width: 0, height: 0 }),
    panToGraphPoint: vi.fn(),
  }),
}))

const originalAdapter = service.defaults.adapter
let wrapper: VueWrapper | undefined
let downloaded: Blob | undefined
let filename: string | undefined

beforeEach(() => {
  downloaded = undefined
  filename = undefined
  vi.spyOn(URL, 'createObjectURL').mockImplementation((blob) => {
    downloaded = blob as Blob
    return 'blob:graphml-test'
  })
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    filename = this.download
  })
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  service.defaults.adapter = originalAdapter
  vi.restoreAllMocks()
})

async function startDownload(surface: 'canvas' | 'reader') {
  const data = graphFixture()
  if (surface === 'canvas') {
    wrapper = mount(GraphCanvas, {
      props: { graphData: data, entityTypes: [] },
      global: { plugins: [makeI18n()] },
    })
    await (wrapper.vm as unknown as { downloadGraphml: () => Promise<void> }).downloadGraphml()
  } else {
    const router = makeRouter()
    await router.push('/graphs/proj_1')
    await router.isReady()
    wrapper = mount(GraphReader, {
      props: { model: buildReaderModel(data), graphData: data },
      global: { plugins: [makeI18n(), router], stubs: { GraphCanvas: CanvasStub } },
    })
    const button = wrapper.findAll('button').find((item) => item.text().includes('GraphML'))
    expect(button).toBeDefined()
    await button!.trigger('click')
  }
  await flushPromises()
}

describe.each(['canvas', 'reader'] as const)('GraphML download via %s', (surface) => {
  it.each([[1, 0], [2, 1], [12, 15]])(
    'preserves XML for %i nodes and %i edges through the actual Axios interceptor',
    async (nodeCount, edgeCount) => {
      const nodes = Array.from({ length: nodeCount }, (_, i) => `<node id="n${i}"/>`).join('')
      const edges = Array.from({ length: edgeCount }, (_, i) => `<edge id="e${i}" source="n0" target="n1"/>`).join('')
      const xml = `<?xml version="1.0" encoding="UTF-8"?><graphml xmlns="http://graphml.graphdrawing.org/xmlns"><graph edgedefault="directed">${nodes}${edges}</graph></graphml>`
      const payload = new Blob([xml], { type: 'application/xml;charset=utf-8' })
      const adapter = vi.fn<AxiosAdapter>(async (config) => ({
        data: payload, status: 200, statusText: 'OK', headers: {}, config,
      }))
      service.defaults.adapter = adapter

      await startDownload(surface)

      expect(adapter).toHaveBeenCalledWith(expect.objectContaining({
        url: '/api/graph/graph_1/export', method: 'get',
        responseType: 'blob', params: { format: 'graphml' },
      }))
      expect(downloaded?.size).toBe(payload.size)
      expect(downloaded).toBe(payload)
      expect(filename).toBe('agora-graph-graph_1.graphml')
      const text = await downloaded!.text()
      expect(text).toBe(xml)
      const document = new DOMParser().parseFromString(text, 'application/xml')
      expect(document.querySelector('parsererror')).toBeNull()
      expect(document.querySelectorAll('node')).toHaveLength(nodeCount)
      expect(document.querySelectorAll('edge')).toHaveLength(edgeCount)
    },
  )

  it('does not create a download when the export request fails', async () => {
    service.defaults.adapter = async () => { throw new Error('Export unavailable') }
    vi.spyOn(console, 'error').mockImplementation(() => {})

    await startDownload(surface)

    expect(URL.createObjectURL).not.toHaveBeenCalled()
    expect(filename).toBeUndefined()
    if (surface === 'reader') {
      expect(wrapper!.get('[role="alert"]').text()).toContain('Export unavailable')
    }
  })

  it('does not download an empty Blob export response', async () => {
    const payload = new Blob([], { type: 'application/xml' })
    const adapter = vi.fn<AxiosAdapter>(async (config) => ({
      data: payload, status: 200, statusText: 'OK', headers: {}, config,
    }))
    service.defaults.adapter = adapter
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    await startDownload(surface)

    expect(URL.createObjectURL).not.toHaveBeenCalled()
    expect(downloaded).toBeUndefined()
    expect(filename).toBeUndefined()
    if (surface === 'canvas') {
      expect(errorSpy).toHaveBeenCalledWith('GraphML export failed', expect.objectContaining({ message: 'GraphML export was empty' }))
    } else {
      expect(wrapper!.get('[role="alert"]').text()).toContain('GraphML export was empty')
    }
  })

  it('does not download a non-Blob export response payload', async () => {
    const payload = { success: true, data: '<graphml/>' } as unknown as Blob
    const adapter = vi.fn<AxiosAdapter>(async (config) => ({
      data: payload, status: 200, statusText: 'OK', headers: {}, config,
    }))
    service.defaults.adapter = adapter
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    await startDownload(surface)

    expect(URL.createObjectURL).not.toHaveBeenCalled()
    expect(downloaded).toBeUndefined()
    expect(filename).toBeUndefined()
    if (surface === 'canvas') {
      expect(errorSpy).toHaveBeenCalledWith('GraphML export failed', expect.objectContaining({ message: 'GraphML export was empty' }))
    } else {
      expect(wrapper!.get('[role="alert"]').text()).toContain('GraphML export was empty')
    }
  })
})
