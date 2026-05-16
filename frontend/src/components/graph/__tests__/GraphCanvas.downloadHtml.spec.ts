// Task 6 — Graph standalone HTML download.
//
// Verifies that GraphCanvas.downloadHtml() emits a Blob-Download mit MIME
// "text/html", einem Filename-Pattern `agora-graph-<gid>.html` und einem
// HTML-Body, der das eingebettete <svg>-Markup enthält. Der eigentliche
// D3-Render läuft in jsdom nicht — graphSvg.value reicht als leere SVG.

import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createI18n } from 'vue-i18n'

import GraphCanvas from '../GraphCanvas.vue'

vi.mock('../../../composables/useGraphRender', () => ({
  useGraphRender: () => ({
    selectedItem: ref(null),
    render: vi.fn(),
    isPaused: ref(false),
    togglePause: vi.fn(),
  }),
}))

vi.mock('../../../api/graph', () => ({
  exportGraphMl: vi.fn(),
}))

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: {
    de: { graph: { ui: { toggleEdgeLabels: 'Edge-Labels' } } },
  },
})

interface CapturedDownload {
  blobType: string
  filename: string
  blob: Blob
}

let captured: CapturedDownload | null = null
let originalCreateObjectURL: typeof URL.createObjectURL
let originalRevokeObjectURL: typeof URL.revokeObjectURL
let originalCreateElement: typeof document.createElement

beforeEach(() => {
  captured = null

  originalCreateObjectURL = URL.createObjectURL
  originalRevokeObjectURL = URL.revokeObjectURL
  originalCreateElement = document.createElement.bind(document)

  URL.createObjectURL = vi.fn((blob: Blob) => {
    captured = {
      blobType: blob.type,
      filename: '<pending>',
      blob,
    }
    return 'blob:mock-url'
  }) as unknown as typeof URL.createObjectURL
  URL.revokeObjectURL = vi.fn() as unknown as typeof URL.revokeObjectURL

  document.createElement = ((tag: string) => {
    const el = originalCreateElement(tag)
    if (tag.toLowerCase() === 'a') {
      Object.defineProperty(el, 'click', {
        value: () => {
          if (captured) captured.filename = (el as HTMLAnchorElement).download
        },
      })
    }
    return el
  }) as typeof document.createElement
})

afterEach(() => {
  URL.createObjectURL = originalCreateObjectURL
  URL.revokeObjectURL = originalRevokeObjectURL
  document.createElement = originalCreateElement
  vi.restoreAllMocks()
})

describe('GraphCanvas.downloadHtml', () => {
  it('builds a standalone HTML Blob with the graph_id in the filename', async () => {
    const wrapper = mount(GraphCanvas, {
      global: { plugins: [i18n] },
      props: {
        graphData: { graph_id: 'gid-42', nodes: [], edges: [] },
        entityTypes: [],
      },
    })

    // The component exposes downloadHtml via defineExpose; in the test runtime
    // we reach it through the component instance.
    const vm = wrapper.vm as unknown as { downloadHtml: () => void }
    vm.downloadHtml()

    expect(captured).not.toBeNull()
    expect(captured!.blobType).toMatch(/^text\/html/)
    expect(captured!.filename).toBe('agora-graph-gid-42.html')
    const text = await captured!.blob.text()
    expect(text).toMatch(/<!doctype html>/i)
    expect(text).toContain('<svg')
    expect(text).toContain('Agora-Graph')
  })

  it('falls back to "graph" as filename slug when graph_id is missing', async () => {
    const wrapper = mount(GraphCanvas, {
      global: { plugins: [i18n] },
      props: {
        graphData: { nodes: [], edges: [] },
        entityTypes: [],
      },
    })

    const vm = wrapper.vm as unknown as { downloadHtml: () => void }
    vm.downloadHtml()

    expect(captured).not.toBeNull()
    expect(captured!.filename).toBe('agora-graph-graph.html')
  })
})
