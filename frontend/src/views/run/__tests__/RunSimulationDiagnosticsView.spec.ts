import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'

const h_ = await vi.hoisted(async () => {
  const { ref } = await import('vue')
  return {
    operator: ref(true),
    fetchLogs: vi.fn(),
    consoleLog: vi.fn(),
  }
})

vi.mock('@/composables/useOperatorAccess', async () => {
  const { computed } = await import('vue')
  return { useOperatorAccess: () => computed(() => h_.operator.value) }
})
vi.mock('@/api/logs', () => ({
  fetchLogs: (...a: unknown[]) => h_.fetchLogs(...a),
  buildLogsStreamUrl: vi.fn().mockResolvedValue('http://localhost/api/logs/stream'),
}))
vi.mock('@/api/simulation', () => ({
  getSimulationConsoleLog: (...a: unknown[]) => h_.consoleLog(...a),
}))
vi.mock('@/composables/useStickyScroll', () => ({
  useStickyScroll: () => ({ unreadCount: { value: 0 }, scrollToBottom: vi.fn(), markAppended: vi.fn() }),
}))
class NoopEventSource {
  onmessage = null
  onerror = null
  close = vi.fn()
}
// @ts-expect-error globales EventSource durch Mock ersetzen
globalThis.EventSource = NoopEventSource

import RunSimulationDiagnosticsView from '../simulation/RunSimulationDiagnosticsView.vue'

const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } })
let wrapper: VueWrapper | null = null

const SERVER_LINES = [
  'INFO sim_2 Executing tool: fremd, parameters: {}',
  'INFO sim_1 Simulation läuft',
  "INFO sim_1 Executing tool: graph_search, parameters: {'q': 'x'}",
  'ERROR sim_1 kaputt',
  'sim_1 Laden:  10%|█   | 1/10',
  'sim_1 Laden:  50%|█████| 5/10',
  'sim_1 Laden: 100%|██████████| 10/10',
]

function logs(lines: string[]) {
  return { data: { success: true, data: { lines, offset: 0 } } }
}

async function mountView() {
  wrapper = mount(RunSimulationDiagnosticsView, {
    props: { simulationId: 'sim_1' },
    global: { plugins: [i18n] },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}
const lineTexts = (w: VueWrapper) => w.findAll('.log-stream .log-line').map((l) => l.text())

beforeEach(() => {
  h_.operator.value = true
  h_.fetchLogs.mockReset().mockResolvedValue(logs(SERVER_LINES))
  h_.consoleLog.mockReset().mockResolvedValue({ success: true, data: { lines: [], from_line: 0, total_lines: 0 } })
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = null
})

describe('RunSimulationDiagnosticsView', () => {
  it('beschränkt das Server-Protokoll auf den Lauf und zeigt nur Tool-Calls, Fehler und Fortschritt', async () => {
    const w = await mountView()
    const lines = lineTexts(w)
    expect(lines).toEqual([
      "INFO sim_1 Executing tool: graph_search, parameters: {'q': 'x'}",
      'ERROR sim_1 kaputt',
      'sim_1 Laden: 100%|██████████| 10/10  (3 Zeilen zusammengefasst)',
    ])
    expect(w.find('.scope-note').text()).toContain('sim_1')
  })

  it('zeigt mit "Alles anzeigen" die ungekürzten Zeilen des Laufs', async () => {
    const w = await mountView()
    await w.find('.kind-all').setValue(true)
    const lines = lineTexts(w)
    expect(lines).toContain('INFO sim_1 Simulation läuft')
    expect(lines.filter((l) => l.includes('Laden:'))).toHaveLength(3)
    expect(lines.join('\n')).not.toContain('sim_2')
  })

  it('zeigt ohne Betreiberzugang einen Hinweis statt des Protokolls', async () => {
    h_.operator.value = false
    const w = await mountView()
    expect(w.find('[data-testid="diagnostics-no-access"]').text()).toContain('gehört dem Betreiber')
    expect(w.find('.log-stream').exists()).toBe(false)
    expect(h_.fetchLogs).not.toHaveBeenCalled()
  })

  it('zeigt das Prozessprotokoll als zweite Quelle mit Verdichtung und Fehlererkennung', async () => {
    h_.consoleLog.mockResolvedValue({
      success: true,
      data: {
        lines: [
          'Round 1/3 (33.3%) done',
          "[ToolUse] Agent calling search_graph({'query': 'x'})",
          '[ToolUse]   -> ERROR: timeout',
          'Batches:  10%|█   | 1/10',
          'Batches: 100%|██████████| 10/10',
        ],
        from_line: 0,
        total_lines: 5,
      },
    })
    const w = await mountView()
    expect(h_.consoleLog).toHaveBeenCalledWith('sim_1', 0)
    const section = w.find('[data-testid="diagnostics-process-log"]')
    expect(section.find('h3').text()).toBe('Simulationsprozess')
    const lines = section.findAll('.dpl__line')
    expect(lines.map((l) => l.text())).toEqual([
      "[ToolUse] Agent calling search_graph({'query': 'x'})",
      '[ToolUse]   -> ERROR: timeout',
      'Batches: 100%|██████████| 10/10  (2 Zeilen zusammengefasst)',
    ])
    expect(lines[1]!.classes()).toContain('is-error')
    await section.find('[data-testid="process-show-all"]').setValue(true)
    expect(section.findAll('.dpl__line')).toHaveLength(5)
  })

  it('zeigt Leerzustand und Fehler des Prozessprotokolls sichtbar', async () => {
    const w = await mountView()
    expect(w.find('[data-testid="process-empty"]').text()).toContain('noch nichts ausgegeben')
    h_.consoleLog.mockResolvedValue({ success: false, error: 'Prozess unbekannt' })
    wrapper!.unmount()
    const w2 = await mountView()
    const err = w2.find('[data-testid="process-error"]')
    expect(err.attributes('role')).toBe('alert')
    expect(err.text()).toContain('Prozess unbekannt')
  })
})
