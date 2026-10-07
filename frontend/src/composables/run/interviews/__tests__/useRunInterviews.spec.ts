import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { ApiError } from '@/api/envelope'

const api = vi.hoisted(() => ({
  askPersonas: vi.fn(),
  getInterviewHistory: vi.fn(),
  getSimulationConfig: vi.fn(),
}))
vi.mock('@/api/interviews', () => ({
  askPersonas: api.askPersonas,
  getInterviewHistory: api.getInterviewHistory,
}))
vi.mock('@/api/simulation', () => ({ getSimulationConfig: api.getSimulationConfig }))

import { GROUP_WARN_THRESHOLD, useRunInterviews } from '../useRunInterviews'
import { INTERVIEW_PROMPT_PREFIX } from '../conversations'

const t = (key: string) => key
const row = (agent_id: number, prompt: string, response: string, timestamp = '2026-10-07T10:00:00') => ({
  agent_id,
  prompt: `${INTERVIEW_PROMPT_PREFIX}${prompt}`,
  response,
  timestamp,
  platform: 'reddit',
})
const ans = (agentId: number, over: Record<string, unknown> = {}) => ({
  agentId,
  platform: 'reddit',
  prompt: 'p',
  response: `A${agentId}`,
  timestamp: '2026-10-07T12:00:00',
  error: null,
  ...over,
})

async function setup() {
  const vm = useRunInterviews('sim_1', { t })
  await flushPromises()
  return vm
}

beforeEach(() => {
  Object.values(api).forEach((m) => m.mockReset())
  api.getInterviewHistory.mockResolvedValue([])
  api.getSimulationConfig.mockResolvedValue({ success: true, data: { llm_model: 'gpt-x' } })
})

describe('useRunInterviews', () => {
  it('lädt Verlauf, bildet Gespräche und liest das Modell des Laufs', async () => {
    api.getInterviewHistory.mockResolvedValue([row(1, 'Frage', 'Antwort')])
    const vm = await setup()
    expect(vm.conversations.value).toHaveLength(1)
    expect(vm.conversations.value[0].turns[0].question).toBe('Frage')
    expect(vm.modelLabel.value).toBe('gpt-x')
    expect(vm.available.value).toBe(true)
    expect(vm.error.value).toBeNull()
  })

  it('zeigt einen Ladefehler sichtbar an', async () => {
    api.getInterviewHistory.mockRejectedValue(new ApiError({ code: 'x', status: 500, message: 'Boom' }))
    const vm = await setup()
    expect(vm.error.value).toContain('Boom')
    expect(vm.conversations.value).toEqual([])
  })

  it('Modell bleibt null, wenn die Konfiguration nicht lesbar ist', async () => {
    api.getSimulationConfig.mockResolvedValue({ success: true, data: { llm_model: null } })
    expect((await setup()).modelLabel.value).toBeNull()
  })

  it('503 beim Fragen setzt available=false mit Grund', async () => {
    api.askPersonas.mockRejectedValue(new ApiError({ code: 'service_unavailable', status: 503, message: 'keine Personas' }))
    const vm = await setup()
    const out = await vm.ask(1, 'Hallo')
    expect(out.status).toBe('unavailable')
    expect(vm.available.value).toBe(false)
    expect(vm.unavailableReason.value).toBe('keine Personas')
  })

  it('ask: hängt die Runde optimistisch an und lädt den Verlauf nach', async () => {
    api.askPersonas.mockResolvedValue([ans(1)])
    api.getInterviewHistory
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([row(1, 'Hallo', 'A1', '2026-10-07T12:00:00')])
    const vm = await setup()
    const out = await vm.ask(1, ' Hallo ')
    expect(out).toEqual({ status: 'answered', answer: 'A1', error: null })
    expect(api.askPersonas).toHaveBeenCalledWith('sim_1', [{ agentId: 1, prompt: 'Hallo' }])
    expect(api.getInterviewHistory).toHaveBeenCalledTimes(2)
    // Kein Doppelzug: die optimistische Runde ist durch den Verlauf ersetzt.
    expect(vm.conversations.value[0].turns).toHaveLength(1)
  })

  it('ask: Fehler im Eintrag bleibt sichtbar und wird nicht verschluckt', async () => {
    api.askPersonas.mockResolvedValue([ans(1, { response: null, error: 'Zeitüberschreitung' })])
    const vm = await setup()
    const out = await vm.ask(1, 'Hallo')
    expect(out).toEqual({ status: 'failed', answer: null, error: 'Zeitüberschreitung' })
    expect(vm.conversations.value[0].turns[0]).toMatchObject({ answer: null, error: 'Zeitüberschreitung' })
    expect(api.getInterviewHistory).toHaveBeenCalledTimes(1)
  })

  it('Envelope-Fehler bei HTTP 200 wird als Anfragefehler gezeigt', async () => {
    api.askPersonas.mockRejectedValue(new ApiError({ code: 'validation_failed', status: 200, message: 'prompt fehlt' }))
    const vm = await setup()
    const out = await vm.ask(1, 'Hallo')
    expect(out.status).toBe('failed')
    expect(vm.sendError.value).toBe('(errors.requestError: prompt fehlt)')
  })

  it('Budgetabbruch wird als solcher durchgereicht', async () => {
    api.askPersonas.mockRejectedValue(
      new ApiError({ code: 'budget_exceeded', status: 409, message: 'Token-Budget überschritten: 10 >= 10' }),
    )
    const vm = await setup()
    const out = await vm.ask(1, 'Hallo')
    expect(out.status).toBe('budget')
    expect(vm.budgetExceeded.value).toBe(true)
    expect(vm.sendError.value).toContain('views.run.interviews.budgetExceeded')
  })

  it('409 budget_exceeded reicht Abbruchgrund und Zahlen aus dem Envelope durch', async () => {
    api.askPersonas.mockRejectedValue(
      new ApiError({
        code: 'budget_exceeded',
        status: 409,
        message: 'Token-Budget überschritten',
        originalResponse: {
          success: false,
          code: 'budget_exceeded',
          error: 'Token-Budget überschritten',
          termination_reason: 'budget_tokens',
          dimension: 'tokens',
          observed: 12000,
          threshold: 10000,
        },
      }),
    )
    const vm = await setup()
    await vm.ask(1, 'Hallo')
    expect(vm.budgetDetail.value).toEqual({
      message: 'Token-Budget überschritten',
      reason: 'budget_tokens',
      dimension: 'tokens',
      observed: 12000,
      threshold: 10000,
    })
  })

  it('409 ohne Zahlen im Body liefert nur die Meldung, nichts Geratenes', async () => {
    api.askPersonas.mockRejectedValue(new ApiError({ code: 'budget_exceeded', status: 409, message: 'voll' }))
    const vm = await setup()
    await vm.ask(1, 'Hallo')
    expect(vm.budgetDetail.value).toMatchObject({ reason: null, observed: null, threshold: null })
  })

  it('Frist-Fehler im Eintrag ist kein Budgetabbruch, der Fehler bleibt am Eintrag', async () => {
    const msg = 'Batch-Deadline von 120s überschritten — Interview nicht mehr gestartet'
    api.askPersonas.mockResolvedValue([ans(1, { response: null, error: msg })])
    const vm = await setup()
    const out = await vm.ask(1, 'x')
    expect(out).toEqual({ status: 'failed', answer: null, error: msg })
    expect(vm.budgetExceeded.value).toBe(false)
    expect(vm.budgetDetail.value).toBeNull()
    expect(vm.conversations.value[0].turns[0]).toMatchObject({ answer: null, error: msg })
  })

  it('Budget-Text im Eintrag oder Code ohne 409 ist kein Budgetabbruch', async () => {
    api.askPersonas.mockResolvedValue([ans(1, { response: null, error: 'Budget exceeded' })])
    const vm = await setup()
    expect((await vm.ask(1, 'x')).status).toBe('failed')
    expect(vm.budgetExceeded.value).toBe(false)
    api.askPersonas.mockRejectedValue(new ApiError({ code: 'budget_exceeded', status: 200, message: 'Budget' }))
    expect((await vm.ask(1, 'y')).status).toBe('failed')
    expect(vm.budgetExceeded.value).toBe(false)
  })

  it('zweite Frage während des Sendens wird verworfen, nur ein Request', async () => {
    let release: (v: unknown[]) => void = () => {}
    api.askPersonas.mockReturnValue(new Promise((r) => { release = r }))
    const vm = await setup()
    const first = vm.ask(1, 'Eins')
    const second = await vm.ask(2, 'Zwei')
    const group = await vm.askGroup([1, 2], 'Drei')
    expect(second).toEqual({ status: 'busy', answer: null, error: null })
    expect(group).toEqual({ asked: 0, answered: 0, failed: 0 })
    expect(api.askPersonas).toHaveBeenCalledTimes(1)
    release([ans(1)])
    expect((await first).status).toBe('answered')
    expect(vm.sending.value).toBe(false)
  })

  it('Wechsel der simulationId während des Sendens: Ergebnis wird verworfen', async () => {
    let release: (v: unknown[]) => void = () => {}
    api.askPersonas.mockReturnValue(new Promise((r) => { release = r }))
    const id = ref('sim_1')
    const vm = useRunInterviews(id, { t })
    await flushPromises()
    const pending = vm.ask(1, 'Hallo')
    id.value = 'sim_2'
    await flushPromises()
    release([ans(1)])
    expect((await pending).status).toBe('stale')
    await flushPromises()
    expect(vm.conversations.value).toEqual([])
    expect(vm.sendError.value).toBeNull()
    expect(vm.sending.value).toBe(false)
    // auch eine Gruppenfrage hinterlässt nichts im neuen Verlauf
    let release2: (v: unknown[]) => void = () => {}
    api.askPersonas.mockReturnValue(new Promise((r) => { release2 = r }))
    const g = vm.askGroup([1, 2], 'Alle')
    id.value = 'sim_3'
    await flushPromises()
    release2([ans(1), ans(2)])
    expect(await g).toEqual({ asked: 0, answered: 0, failed: 0 })
    expect(vm.groupResults.value).toEqual([])
    expect(vm.conversations.value).toEqual([])
  })

  it('verspätete Modell-Antwort einer alten Simulation überschreibt das Modell nicht', async () => {
    let release: (v: unknown) => void = () => {}
    api.getSimulationConfig
      .mockReturnValueOnce(new Promise((r) => { release = r }))
      .mockResolvedValueOnce({ success: true, data: { llm_model: 'neu' } })
    const id = ref('sim_1')
    const vm = useRunInterviews(id, { t })
    id.value = 'sim_2'
    await flushPromises()
    release({ success: true, data: { llm_model: 'alt' } })
    await flushPromises()
    expect(vm.modelLabel.value).toBe('neu')
  })

  it('Fehler beim Laden des Modells wird protokolliert, Anzeige bleibt "unbekannt"', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    api.getSimulationConfig.mockRejectedValue(new Error('weg'))
    const vm = await setup()
    expect(vm.modelLabel.value).toBeNull()
    expect(warn).toHaveBeenCalledWith('[run-interviews] Modell des Laufs nicht ladbar', expect.objectContaining({ error: 'weg' }))
    warn.mockRestore()
  })

  it('askGroup: Teilfehler je Persona, Gruppe nur für die Sitzung, Zähler stimmen', async () => {
    api.askPersonas.mockResolvedValue([ans(1), ans(2, { response: null, error: 'kaputt' })])
    const vm = await setup()
    const out = await vm.askGroup([1, 2, 3], 'Alle')
    // Persona 3 fehlt in der Antwort: zählt als fehlgeschlagen, nicht als leere Antwort.
    expect(out).toEqual({ asked: 3, answered: 1, failed: 2 })
    const g = vm.groupResults.value[0]
    expect(g.conversationId).toMatch(/^group-[A-Za-z0-9_-]+$/)
    expect(g.answers.map((a) => [a.agentId, a.answer, a.error])).toEqual([
      [1, 'A1', null],
      [2, null, 'kaputt'],
      [3, null, 'views.run.interviews.noAnswer'],
    ])
  })

  it('askGroup ohne Personas oder Text sendet nichts', async () => {
    const vm = await setup()
    expect(await vm.askGroup([], 'x')).toEqual({ asked: 0, answered: 0, failed: 0 })
    expect(await vm.askGroup([1], '  ')).toEqual({ asked: 0, answered: 0, failed: 0 })
    expect(api.askPersonas).not.toHaveBeenCalled()
  })

  it('largeGroupWarning schlägt oberhalb der Schwelle an', async () => {
    const vm = await setup()
    expect(vm.largeGroupWarning(GROUP_WARN_THRESHOLD)).toBe(false)
    expect(vm.largeGroupWarning(GROUP_WARN_THRESHOLD + 1)).toBe(true)
  })

  it('Gespräche aus dem Server-Verlauf werden nie zu Gruppen', async () => {
    api.getInterviewHistory.mockResolvedValue([row(1, 'Gleich', 'a'), row(2, 'Gleich', 'b')])
    const vm = await setup()
    expect(vm.groupResults.value).toEqual([])
    expect(vm.conversations.value).toHaveLength(2)
  })
})
