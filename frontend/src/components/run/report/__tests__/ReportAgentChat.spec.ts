import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { ApiError } from '@/api/envelope'

const api = vi.hoisted(() => ({ chatWithReport: vi.fn() }))
vi.mock('@/api/report', async (importOriginal) => ({ ...(await importOriginal<object>()), ...api }))

import ReportAgentChat from '../ReportAgentChat.vue'
import { resetReportAgentChats } from '@/composables/run/report/useReportAgentChat'
import { listEnvelope, reportData } from '@/composables/run/report/__tests__/reportFixtures'
import { mountWithReport, okApi } from './helpers'

const ok = (response: unknown) => ({ success: true, data: { response } })

async function mountChat(apiOver: Record<string, unknown> = {}) {
  return mountWithReport(ReportAgentChat, { simulationId: 'sim_1' }, { api: okApi(apiOver) })
}

async function ask(wrapper: Awaited<ReturnType<typeof mountChat>>['wrapper'], text: string) {
  await wrapper.get('[data-testid="report-chat-input"]').setValue(text)
  await wrapper.get('[data-testid="report-chat-send"]').trigger('click')
  await flushPromises()
}

describe('ReportAgentChat', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetReportAgentChats()
  })

  it('Eingabe hat ein echtes label[for]; ein Satz nennt, dass der Chat am Lauf hängt', async () => {
    const { wrapper } = await mountChat()
    const input = wrapper.get('[data-testid="report-chat-input"]')
    const label = wrapper.get(`label[for="${input.attributes('id')}"]`)
    expect(label.text()).toBe('Frage an den Berichtsagenten')
    expect(wrapper.get('[data-testid="report-chat-scope"]').text()).toContain('gelten für den ganzen Lauf')
  })

  it('sendet simulation_id, Nachricht und bisherigen Verlauf im Format des Bestands', async () => {
    api.chatWithReport.mockResolvedValueOnce(ok({ response: 'Erste Antwort', tool_calls: [], sources: [] }))
    api.chatWithReport.mockResolvedValueOnce(ok('Zweite Antwort'))
    const { wrapper } = await mountChat()
    await ask(wrapper, 'Wer widerspricht?')
    expect(api.chatWithReport).toHaveBeenNthCalledWith(1, { simulation_id: 'sim_1', message: 'Wer widerspricht?', chat_history: [] })
    await ask(wrapper, 'Und warum?')
    expect(api.chatWithReport).toHaveBeenNthCalledWith(2, {
      simulation_id: 'sim_1',
      message: 'Und warum?',
      chat_history: [
        { role: 'user', content: 'Wer widerspricht?' },
        { role: 'assistant', content: 'Erste Antwort' },
      ],
    })
    const log = wrapper.get('[data-testid="report-chat-log"]')
    expect(log.text()).toContain('Wer widerspricht?')
    expect(log.text()).toContain('Zweite Antwort')
    expect((wrapper.get('[data-testid="report-chat-input"]').element as HTMLTextAreaElement).value).toBe('')
  })

  it('Antworten sind mit Text als Modellausgabe gekennzeichnet', async () => {
    api.chatWithReport.mockResolvedValue(ok('Antwort'))
    const { wrapper } = await mountChat()
    await ask(wrapper, 'Frage')
    const mark = wrapper.get('[data-testid="report-chat-answer"] [data-testid="report-chat-mark"]')
    expect(mark.text()).toBe('SIM')
    expect(wrapper.get('[data-testid="report-chat-answer"]').text()).toContain('Modellausgabe')
  })

  it('rendert Markdown gesäubert: kein script, kein onerror', async () => {
    api.chatWithReport.mockResolvedValue(
      ok('**fett** <script>window.__pwn = 1</script><img src=x onerror="window.__pwn = 2">'),
    )
    const { wrapper } = await mountChat()
    await ask(wrapper, 'Frage')
    const body = wrapper.get('[data-testid="report-chat-answer"] .rac__body')
    expect(body.find('strong').text()).toBe('fett')
    expect(body.html()).not.toMatch(/<script/i)
    expect(body.html()).not.toMatch(/onerror/i)
  })

  it('Fehler des Backends bleiben sichtbar (Budget-/Ratenlimit), nie als leere Antwort, und gehen nicht in den Verlauf', async () => {
    api.chatWithReport.mockRejectedValueOnce(
      new ApiError({ code: 'budget_exceeded', status: 429, message: 'Budget für diesen Lauf ausgeschöpft' }),
    )
    api.chatWithReport.mockResolvedValueOnce(ok('Antwort'))
    const { wrapper } = await mountChat()
    await ask(wrapper, 'Frage')
    const alert = wrapper.get('[data-testid="report-chat-error"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('Anfragefehler')
    expect(alert.text()).toContain('Budget für diesen Lauf ausgeschöpft')
    await ask(wrapper, 'Nochmal')
    expect(api.chatWithReport.mock.calls[1]![0].chat_history).toEqual([{ role: 'user', content: 'Frage' }])
  })

  it('Fehlerhülle (success=false) und Antwort ohne Text sind Fehler, keine leere Antwort', async () => {
    api.chatWithReport.mockResolvedValueOnce({ success: false, error: 'Berichtsagent nicht verfügbar' })
    api.chatWithReport.mockResolvedValueOnce(ok({ tool_calls: [] }))
    const { wrapper } = await mountChat()
    await ask(wrapper, 'A')
    expect(wrapper.get('[data-testid="report-chat-error"]').text()).toContain('Berichtsagent nicht verfügbar')
    await ask(wrapper, 'B')
    const errors = wrapper.findAll('[data-testid="report-chat-error"]')
    expect(errors[1]!.text()).toContain('Keine Antwort erhalten')
    expect(wrapper.findAll('[data-testid="report-chat-answer"]')).toHaveLength(0)
  })

  it('Sendezustand ist in einer aria-live-Region sichtbar und sperrt doppeltes Senden', async () => {
    let resolve!: (v: unknown) => void
    api.chatWithReport.mockReturnValue(new Promise((r) => (resolve = r)))
    const { wrapper } = await mountChat()
    await wrapper.get('[data-testid="report-chat-input"]').setValue('Frage')
    await wrapper.get('[data-testid="report-chat-send"]').trigger('click')
    const status = wrapper.get('[data-testid="report-chat-status"]')
    expect(status.attributes('aria-live')).toBe('polite')
    expect(status.text()).toContain('antwortet')
    await wrapper.get('[data-testid="report-chat-input"]').setValue('Zweite')
    await wrapper.get('[data-testid="report-chat-send"]').trigger('click')
    expect(api.chatWithReport).toHaveBeenCalledTimes(1)
    resolve(ok('fertig'))
    await flushPromises()
    expect(status.text()).toBe('')
  })

  it('Strg+Enter und Cmd+Enter senden, einfaches Enter nicht', async () => {
    api.chatWithReport.mockResolvedValue(ok('A'))
    const { wrapper } = await mountChat()
    const input = wrapper.get('[data-testid="report-chat-input"]')
    await input.setValue('Frage 1')
    await input.trigger('keydown', { key: 'Enter' })
    expect(api.chatWithReport).not.toHaveBeenCalled()
    await input.trigger('keydown', { key: 'Enter', ctrlKey: true })
    await flushPromises()
    expect(api.chatWithReport).toHaveBeenCalledTimes(1)
    await input.setValue('Frage 2')
    await input.trigger('keydown', { key: 'Enter', metaKey: true })
    await flushPromises()
    expect(api.chatWithReport).toHaveBeenCalledTimes(2)
  })

  it('der Verlauf lebt je Lauf für die Sitzung; „Verlauf leeren“ leert nur diesen Lauf', async () => {
    api.chatWithReport.mockResolvedValue(ok('A'))
    const first = await mountChat()
    await ask(first.wrapper, 'Frage zu Lauf 1')
    first.wrapper.unmount()

    const again = await mountChat()
    expect(again.wrapper.get('[data-testid="report-chat-log"]').text()).toContain('Frage zu Lauf 1')

    const other = await mountWithReport(ReportAgentChat, { simulationId: 'sim_2' }, { api: okApi() })
    expect(other.wrapper.find('[data-testid="report-chat-log"]').text()).not.toContain('Frage zu Lauf 1')
    other.wrapper.unmount()

    await again.wrapper.get('[data-testid="report-chat-clear"]').trigger('click')
    expect(again.wrapper.get('[data-testid="report-chat-log"]').text()).not.toContain('Frage zu Lauf 1')
    expect(again.wrapper.get('[data-testid="report-chat-clear"]').attributes('disabled')).toBeDefined()
  })

  it('ohne Berichtsfassung: Erklärung statt Eingabefeld', async () => {
    const { wrapper } = await mountChat({ listReports: vi.fn().mockResolvedValue(listEnvelope([])) })
    expect(wrapper.find('[data-testid="report-chat-input"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="report-chat-unavailable"]').text()).toContain('mindestens eine Berichtsfassung')
  })

  it('eine unvollständige Fassung genügt, der Chat bleibt nutzbar', async () => {
    const inc = reportData({ status: 'incomplete', missing_sections: ['Akteure'] })
    const { wrapper } = await mountChat({
      listReports: vi.fn().mockResolvedValue(listEnvelope([inc])),
      getReport: vi.fn().mockResolvedValue({ success: true, data: inc }),
    })
    expect(wrapper.find('[data-testid="report-chat-input"]').exists()).toBe(true)
  })
})
