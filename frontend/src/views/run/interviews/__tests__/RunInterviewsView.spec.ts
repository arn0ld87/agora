import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { RouterView, createMemoryHistory, createRouter } from 'vue-router'
import { computed, defineComponent, h, provide, ref } from 'vue'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import { ApiError } from '@/api/envelope'

const api = vi.hoisted(() => ({
  askPersonas: vi.fn(),
  getInterviewHistory: vi.fn(),
  getSimulationConfig: vi.fn(),
}))
vi.mock('@/api/interviews', () => ({ askPersonas: api.askPersonas, getInterviewHistory: api.getInterviewHistory }))
vi.mock('@/api/simulation', () => ({ getSimulationConfig: api.getSimulationConfig }))

const download = vi.hoisted(() => ({ triggerDownload: vi.fn() }))
vi.mock('@/composables/useReportExports', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/composables/useReportExports')>()),
  triggerDownload: download.triggerDownload,
}))

const refs = vi.hoisted(() => ({
  evidence: vi.fn(),
  posts: [] as { persona_id: string }[],
}))
vi.mock('@/api/report', () => ({ getReportEvidence: refs.evidence }))
vi.mock('@/composables/run/simulation/useRunFeed', () => ({
  useRunFeed: () => ({
    posts: { value: refs.posts },
    truncated: { value: false },
    error: { value: null },
    reload: vi.fn().mockResolvedValue(undefined),
  }),
}))

const persona = (id: number, name: string) => ({
  personaId: String(id),
  name,
  username: null,
  role: 'Landrätin',
  bio: null,
  stance: 'dafür',
  contestedQuestion: null,
})
const PERSONAS = [persona(0, 'Anke Wübbena'), persona(1, 'Jörg Kreistag')]
vi.mock('@/composables/run/simulation/useRunPersonas', () => ({
  useRunPersonas: () => ({
    loading: computed(() => false),
    error: computed(() => null),
    contestedQuestion: computed(() => null),
    personaById: (id: string) => PERSONAS.find((p) => p.personaId === id) ?? null,
    personas: computed(() => PERSONAS),
    reload: vi.fn(),
  }),
}))

import RunInterviewsView from '../RunInterviewsView.vue'
import { RUN_WORKSPACE_KEY, type RunWorkspace } from '@/composables/run/useRunWorkspace'
import { INTERVIEW_PROMPT_PREFIX } from '@/composables/run/interviews/conversations'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'de', messages: { de } })

function workspaceWith(simState: string, reportId: string | null = null, loadState = 'ready') {
  return {
    state: ref(loadState),
    stages: computed(() => [{ key: 'simulation', state: simState }]),
    data: computed(() => ({ reports: reportId ? [{ reportId }] : [] })),
    tabs: computed(() => [
      { key: 'report', to: reportId ? { name: 'RunReportTab', params: { reportId } } : null, disabledReason: null },
    ]),
  } as unknown as RunWorkspace
}

async function mountAt(
  path: string,
  simState: string | null = 'done',
  reportId: string | null = null,
  loadState = 'ready',
) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/simulations/:simulationId/interviews/:conversationId?',
        name: 'RunInterviews',
        component: RunInterviewsView,
        props: true,
      },
      { path: '/simulations/:simulationId/feed', name: 'RunSimulationFeed', component: { template: '<div />' } },
      { path: '/report/:reportId', name: 'RunReportTab', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  const Host = defineComponent({
    setup() {
      if (simState) provide(RUN_WORKSPACE_KEY, workspaceWith(simState, reportId, loadState))
      return () => h(RouterView)
    },
  })
  const w = mount(Host, { global: { plugins: [router, i18n] }, attachTo: document.body })
  await flushPromises()
  return { w, router }
}

const hist = (agent_id: number, prompt: string, response: string) => ({
  agent_id,
  prompt: `${INTERVIEW_PROMPT_PREFIX}${prompt}`,
  response,
  timestamp: '2026-10-07T10:00:00',
  platform: 'reddit',
})

beforeEach(() => {
  Object.values(api).forEach((m) => m.mockReset())
  download.triggerDownload.mockReset()
  api.getInterviewHistory.mockResolvedValue([])
  api.getSimulationConfig.mockResolvedValue({ success: true, data: { llm_model: 'gpt-x' } })
  refs.evidence.mockReset()
  refs.evidence.mockResolvedValue({ success: false, code: 'not_found', error: 'x' })
  refs.posts = []
  document.body.innerHTML = ''
})

describe('RunInterviewsView', () => {
  it('zeigt "Noch kein Gespräch" ohne Verlauf und hat keinen h1', async () => {
    const { w } = await mountAt('/simulations/sim_1/interviews')
    expect(w.get('[data-testid="list-empty"]').text()).toBe('Noch kein Gespräch')
    expect(w.get('[data-testid="pane-empty"]').text()).toBe('Noch kein Gespräch')
    expect(w.find('h1').exists()).toBe(false)
  })

  it('zeigt den Ladezustand', async () => {
    api.getInterviewHistory.mockReturnValue(new Promise(() => {}))
    const { w } = await mountAt('/simulations/sim_1/interviews')
    expect(w.get('[data-testid="interviews-loading"]').attributes('role')).toBe('status')
  })

  it('zeigt einen Ladefehler als Alert und lädt auf Knopfdruck neu', async () => {
    api.getInterviewHistory.mockRejectedValueOnce(new ApiError({ code: 'x', status: 500, message: 'Boom' }))
    const { w } = await mountAt('/simulations/sim_1/interviews')
    const alert = w.get('[data-testid="interviews-error"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('Boom')
    await w.get('[data-testid="interviews-retry"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="interviews-error"]').exists()).toBe(false)
  })

  it('listet Gespräche aus dem Verlauf; die Auswahl ändert die Adresse und zeigt den Verlauf', async () => {
    api.getInterviewHistory.mockResolvedValue([hist(1, 'Was sagen Sie?', 'Das lehne ich ab.')])
    const { w, router } = await mountAt('/simulations/sim_1/interviews')
    const items = w.findAll('[data-testid="conversation-item"]')
    expect(items).toHaveLength(1)
    expect(items[0].text()).toContain('Jörg Kreistag')

    await items[0].trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.params.conversationId).toBe('persona-1')
    expect(w.get('[data-testid="pane-title"]').text()).toContain('Jörg Kreistag')
    expect(w.get('[data-testid="turns"]').text()).toContain('Was sagen Sie?')
    expect(w.get('[data-testid="turn-answer"]').text()).toContain('Das lehne ich ab.')
    const marks = w.get('[data-testid="turn-answer"]').text()
    expect(marks).toContain('SIM')
    expect(marks).toContain('Interview')
    expect(w.get('[data-testid="persona-card-name"]').text()).toBe('Jörg Kreistag')
    expect(w.get('[data-testid="ask-model"]').text()).toContain('gpt-x')
  })

  it('"Neues Gespräch" öffnet die gewählte Persona unter eigener Adresse', async () => {
    const { w, router } = await mountAt('/simulations/sim_1/interviews')
    await w.get('[data-testid="new-persona"]').setValue('0')
    await w.get('[data-testid="new-open"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.params.conversationId).toBe('persona-0')
    expect(w.find('[data-testid="pane-no-turns"]').exists()).toBe(true)
  })

  it('Senden ruft ask mit Persona und Text auf', async () => {
    api.askPersonas.mockResolvedValue([
      { agentId: 0, platform: 'reddit', prompt: 'p', response: 'Antwort', timestamp: '2026-10-07T12:00:00', error: null },
    ])
    const { w } = await mountAt('/simulations/sim_1/interviews/persona-0')
    await w.get('[data-testid="ask-input"]').setValue('Wie stehen Sie dazu?')
    await w.get('[data-testid="ask-form"]').trigger('submit')
    await flushPromises()
    expect(api.askPersonas).toHaveBeenCalledWith('sim_1', [{ agentId: 0, prompt: 'Wie stehen Sie dazu?' }])
    expect(w.get('[data-testid="turn-answer"]').text()).toContain('Antwort')
  })

  it('zeigt einen Fehler je Antwort statt einer leeren Antwort', async () => {
    api.askPersonas.mockResolvedValue([
      { agentId: 0, platform: 'reddit', prompt: null, response: null, timestamp: null, error: 'Zeitüberschreitung' },
    ])
    const { w } = await mountAt('/simulations/sim_1/interviews/persona-0')
    await w.get('[data-testid="ask-input"]').setValue('Hallo')
    await w.get('[data-testid="ask-form"]').trigger('submit')
    await flushPromises()
    expect(w.get('[data-testid="ask-error"]').attributes('role')).toBe('alert')
    expect(w.get('[data-testid="turn-error"]').text()).toContain('Zeitüberschreitung')
  })

  it('503 zeigt "nicht verfügbar" mit Grund und sperrt das Eingabefeld', async () => {
    api.askPersonas.mockRejectedValue(
      new ApiError({ code: 'service_unavailable', status: 503, message: 'Keine Personas gespeichert' }),
    )
    const { w } = await mountAt('/simulations/sim_1/interviews/persona-0')
    await w.get('[data-testid="ask-input"]').setValue('Hallo')
    await w.get('[data-testid="ask-form"]').trigger('submit')
    await flushPromises()
    const box = w.get('[data-testid="interviews-unavailable"]')
    expect(box.text()).toContain('Keine Personas gespeichert')
    expect(w.find('[data-testid="ask-form"]').exists()).toBe(false)
  })

  it('ohne abgeschlossene Simulation steht ein Hinweis statt des Eingabefelds', async () => {
    const { w } = await mountAt('/simulations/sim_1/interviews/persona-0', 'running')
    expect(w.get('[data-testid="interviews-not-run"]').text()).toContain('abgeschlossen')
    expect(w.find('[data-testid="ask-form"]').exists()).toBe(false)
    expect(w.find('[data-testid="ask-blocked"]').exists()).toBe(true)
  })

  it('Gruppenfrage bleibt gesperrt, solange die Simulation läuft', async () => {
    const { w } = await mountAt('/simulations/sim_1/interviews', 'running')
    await w.get('[data-testid="group-toggle"]').trigger('click')
    const boxes = w.findAll('input[type="checkbox"]')
    await boxes[0].setValue(true)
    await w.get('[data-testid="group-text"]').setValue('Frage an alle')
    const send = w.get('[data-testid="group-send"]')
    expect(send.attributes('disabled')).toBeDefined()
    await send.trigger('click')
    expect(api.askPersonas).not.toHaveBeenCalled()
  })

  it('ohne Arbeitsbereich oder bei ungeladenem Zustand bleibt die Eingabe gesperrt (fail-closed)', async () => {
    const none = await mountAt('/simulations/sim_1/interviews/persona-0', null)
    expect(none.w.find('[data-testid="ask-form"]').exists()).toBe(false)
    expect(none.w.get('[data-testid="interviews-state-unknown"]').attributes('role')).toBe('status')
    none.w.unmount()
    const loading = await mountAt('/simulations/sim_1/interviews/persona-0', 'done', null, 'loading')
    expect(loading.w.find('[data-testid="ask-form"]').exists()).toBe(false)
    expect(loading.w.find('[data-testid="interviews-state-unknown"]').exists()).toBe(true)
  })

  it('unbekannte oder nicht mehr vorhandene Gruppe zeigt einen ruhigen Leerzustand', async () => {
    const { w } = await mountAt('/simulations/sim_1/interviews/group-weg')
    expect(w.get('[data-testid="pane-group-missing"]').text()).toContain('nur in der Sitzung')
    expect(w.find('[data-testid="ask-form"]').exists()).toBe(false)
  })

  it('Antwort wird höflich angesagt und der Fokus bleibt im Eingabefeld', async () => {
    api.askPersonas.mockResolvedValue([
      { agentId: 0, platform: 'reddit', prompt: 'p', response: 'Antwort', timestamp: '2026-10-07T12:00:00', error: null },
    ])
    const { w } = await mountAt('/simulations/sim_1/interviews/persona-0')
    await w.get('[data-testid="ask-input"]').setValue('Hallo')
    await w.get('[data-testid="ask-form"]').trigger('submit')
    await flushPromises()
    const status = w.get('[data-testid="ask-status"]')
    expect(status.attributes('aria-live')).toBe('polite')
    expect(status.text()).toContain('Anke Wübbena')
    expect(document.activeElement).toBe(w.get('[data-testid="ask-input"]').element)
  })

  it('unbekanntes conversationId-Format wird wie keine Auswahl behandelt (Router liefert es nicht durch)', async () => {
    const { w } = await mountAt('/simulations/sim_1/interviews')
    expect(w.find('[data-testid="turns"]').exists()).toBe(false)
  })

  it('Gruppenfrage: Warnung bei vielen Personas, Ergebnis je Persona, Adresse der Gruppe', async () => {
    api.askPersonas.mockResolvedValue([
      { agentId: 0, platform: 'reddit', prompt: 'p', response: 'Ja', timestamp: '2026-10-07T12:00:00', error: null },
      { agentId: 1, platform: 'reddit', prompt: null, response: null, timestamp: null, error: 'kaputt' },
    ])
    const { w, router } = await mountAt('/simulations/sim_1/interviews')
    await w.get('[data-testid="group-toggle"]').trigger('click')
    const boxes = w.findAll('input[type="checkbox"]')
    expect(boxes).toHaveLength(2)
    await boxes[0].setValue(true)
    await boxes[1].setValue(true)
    await w.get('[data-testid="group-text"]').setValue('Frage an alle')
    await w.get('[data-testid="group-send"]').trigger('click')
    await flushPromises()
    expect(api.askPersonas).toHaveBeenCalledWith('sim_1', [
      { agentId: 0, prompt: 'Frage an alle' },
      { agentId: 1, prompt: 'Frage an alle' },
    ])
    expect(w.get('[data-testid="group-summary"]').text()).toBe('2 gefragt, 1 beantwortet, 1 fehlgeschlagen')
    expect(router.currentRoute.value.params.conversationId).toMatch(/^group-/)
    expect(w.get('[data-testid="group-answers"]').text()).toContain('kaputt')
  })

  it('Gruppenfrage: Antworten nebeneinander mit Zählzeile und Verweis ins Einzelgespräch', async () => {
    api.askPersonas.mockResolvedValue([
      { agentId: 0, platform: 'reddit', prompt: 'p', response: 'Ja', timestamp: '2026-10-07T12:00:00', error: null },
      { agentId: 1, platform: 'reddit', prompt: null, response: null, timestamp: null, error: 'kaputt' },
    ])
    const { w, router } = await mountAt('/simulations/sim_1/interviews')
    await w.get('[data-testid="group-toggle"]').trigger('click')
    const boxes = w.findAll('input[type="checkbox"]')
    await boxes[0].setValue(true)
    await boxes[1].setValue(true)
    expect(w.get('[data-testid="group-cost"]').text()).toContain('2 Aufrufe')
    await w.get('[data-testid="group-text"]').setValue('Frage an alle')
    await w.get('[data-testid="group-send"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="group-count"]').text()).toBe('1 von 2 beantwortet')
    expect(w.get('[data-testid="group-answers"]').classes()).toContain('cpane__grid')
    expect(w.findAll('[data-testid="group-answer"]')).toHaveLength(1)
    expect(w.get('[data-testid="group-answer-error"]').text()).toContain('kaputt')
    const links = w.findAll('[data-testid="group-answer-link"]')
    expect(links).toHaveLength(2)
    await links[0].trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.params.conversationId).toBe('persona-0')
  })

  it('zeigt den Kostenhinweis und sendet per Strg+Enter', async () => {
    api.askPersonas.mockResolvedValue([
      { agentId: 0, platform: 'reddit', prompt: 'p', response: 'Antwort', timestamp: '2026-10-07T12:00:00', error: null },
    ])
    const { w } = await mountAt('/simulations/sim_1/interviews/persona-0')
    expect(w.get('[data-testid="ask-cost"]').text()).toContain('zählt aufs Budget des Laufs')
    await w.get('[data-testid="ask-input"]').setValue('Hallo')
    await w.get('[data-testid="ask-input"]').trigger('keydown', { key: 'Enter', ctrlKey: true })
    await flushPromises()
    expect(api.askPersonas).toHaveBeenCalledTimes(1)
  })

  it('Budgetabbruch (409) steht dauerhaft mit Grund und Zahlen da, nie als leere Antwort', async () => {
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
    const { w, router } = await mountAt('/simulations/sim_1/interviews/persona-0')
    await w.get('[data-testid="ask-input"]').setValue('Hallo')
    await w.get('[data-testid="ask-form"]').trigger('submit')
    await flushPromises()
    const box = w.get('[data-testid="budget-notice"]')
    expect(box.attributes('role')).toBe('alert')
    expect(w.get('[data-testid="budget-reason"]').text()).toContain('budget_tokens')
    expect(w.get('[data-testid="budget-figures"]').text()).toBe('tokens: 12000 von 10000')
    expect(w.find('[data-testid="turn-answer"]').exists()).toBe(false)
    // Das Feld bleibt, die Meldung bleibt auch beim Wechsel des Gesprächs.
    expect(w.find('[data-testid="ask-form"]').exists()).toBe(true)
    await router.push('/simulations/sim_1/interviews/persona-1')
    await flushPromises()
    expect(w.find('[data-testid="budget-notice"]').exists()).toBe(true)
  })

  it('Deep-Link auf eine Persona ohne Verlauf öffnet ein leeres Gespräch, eine unbekannte wird gemeldet', async () => {
    const known = await mountAt('/simulations/sim_1/interviews/persona-1')
    expect(known.w.find('[data-testid="pane-no-turns"]').exists()).toBe(true)
    expect(known.w.find('[data-testid="pane-unknown-persona"]').exists()).toBe(false)
    expect(known.w.find('[data-testid="ask-form"]').exists()).toBe(true)
    known.w.unmount()
    const unknown = await mountAt('/simulations/sim_1/interviews/persona-42')
    expect(unknown.w.get('[data-testid="pane-unknown-persona"]').text()).toContain('42')
    expect(unknown.w.find('[data-testid="ask-form"]').exists()).toBe(false)
  })

  it('Persona-Spalte: Feed-Sprung mit Zahl und Personen-Filter, Bericht nur mit belegter Zahl', async () => {
    refs.posts = [{ persona_id: '0' }, { persona_id: '0' }, { persona_id: '1' }]
    refs.evidence.mockResolvedValue({
      success: true,
      data: {
        evidence_index: {
          e1: { evidence_id: 'e1', voice_key: 'agent:0' },
          e2: { evidence_id: 'e2', voice_key: 'agent:0' },
          e3: { evidence_id: 'e3', voice_key: 'agent:1' },
          e4: { evidence_id: 'e4', voice_key: null },
        },
      },
    })
    const { w, router } = await mountAt('/simulations/sim_1/interviews/persona-0', 'done', 'rep_1')
    const feed = w.get('[data-testid="persona-feed-link"]')
    expect(feed.text()).toBe('Beiträge im Feed (2) →')
    const report = w.get('[data-testid="persona-report-link"]')
    expect(report.text()).toBe('Im Bericht zitiert (2) →')
    await feed.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('RunSimulationFeed')
    expect(router.currentRoute.value.query.persona).toBe('0')
  })

  it('ohne lesbare Evidence fehlt die Berichtszeile, der Feed-Sprung bleibt', async () => {
    const { w } = await mountAt('/simulations/sim_1/interviews/persona-0', 'done', 'rep_1')
    expect(w.find('[data-testid="persona-report-link"]').exists()).toBe(false)
    expect(w.find('[data-testid="persona-report-none"]').exists()).toBe(false)
    expect(w.find('[data-testid="persona-feed-link"]').exists()).toBe(true)
  })

  it('Gruppengespräch: Persona-Spalte listet die Beteiligten mit Sprung ins Einzelgespräch', async () => {
    api.askPersonas.mockResolvedValue([
      { agentId: 0, platform: 'reddit', prompt: 'p', response: 'Ja', timestamp: '2026-10-07T12:00:00', error: null },
      { agentId: 1, platform: 'reddit', prompt: 'p', response: 'Nein', timestamp: '2026-10-07T12:00:00', error: null },
    ])
    const { w, router } = await mountAt('/simulations/sim_1/interviews')
    await w.get('[data-testid="group-toggle"]').trigger('click')
    const boxes = w.findAll('input[type="checkbox"]')
    await boxes[0].setValue(true)
    await boxes[1].setValue(true)
    await w.get('[data-testid="group-text"]').setValue('Frage')
    await w.get('[data-testid="group-send"]').trigger('click')
    await flushPromises()
    const links = w.findAll('[data-testid="group-participant-link"]')
    expect(links.map((l) => l.text())).toEqual(['Anke Wübbena', 'Jörg Kreistag'])
    await links[1].trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.params.conversationId).toBe('persona-1')
  })

  it('Antwort lässt sich kopieren', async () => {
    api.getInterviewHistory.mockResolvedValue([hist(0, 'Frage?', 'Kopierbar')])
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    const { w } = await mountAt('/simulations/sim_1/interviews/persona-0')
    await w.get('[data-testid="turn-copy"]').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('Kopierbar')
    expect(w.get('[data-testid="copy-status"]').text()).toContain('kopiert')
  })

  describe('Umfrage (#1790)', () => {
    async function askAll(w: Awaited<ReturnType<typeof mountAt>>['w'], text = 'Frage an alle') {
      await w.get('[data-testid="group-toggle"]').trigger('click')
      await w.get('[data-testid="group-select-all"]').trigger('click')
      await w.get('[data-testid="group-text"]').setValue(text)
      await w.get('[data-testid="group-send"]').trigger('click')
      await flushPromises()
    }

    it('Alle auswählen und Alle abwählen setzen die Häkchen, die Zählzeile folgt', async () => {
      const { w } = await mountAt('/simulations/sim_1/interviews')
      await w.get('[data-testid="group-toggle"]').trigger('click')
      expect(w.get('[data-testid="group-selected"]').text()).toBe('Keine Persona ausgewählt')
      await w.get('[data-testid="group-select-all"]').trigger('click')
      const boxes = w.findAll('input[type="checkbox"]')
      expect(boxes.every((b) => (b.element as HTMLInputElement).checked)).toBe(true)
      expect(w.get('[data-testid="group-selected"]').text()).toBe('2 von 2 Personas ausgewählt')
      expect(w.get('[data-testid="group-selected"]').attributes('aria-live')).toBe('polite')
      expect(w.get('[data-testid="group-cost"]').text()).toContain('2 Aufrufe')
      await w.get('[data-testid="group-clear"]').trigger('click')
      expect(boxes.some((b) => (b.element as HTMLInputElement).checked)).toBe(false)
      expect(w.get('[data-testid="group-selected"]').text()).toBe('Keine Persona ausgewählt')
    })

    it('Senden ruft den Sendepfad mit allen gewählten IDs auf', async () => {
      api.askPersonas.mockResolvedValue([
        { agentId: 0, platform: 'reddit', prompt: 'p', response: 'Ja', timestamp: '2026-10-07T12:00:00', error: null },
        { agentId: 1, platform: 'reddit', prompt: 'p', response: 'Nein', timestamp: '2026-10-07T12:00:00', error: null },
      ])
      const { w } = await mountAt('/simulations/sim_1/interviews')
      await askAll(w)
      expect(api.askPersonas).toHaveBeenCalledWith('sim_1', [
        { agentId: 0, prompt: 'Frage an alle' },
        { agentId: 1, prompt: 'Frage an alle' },
      ])
    })

    it('ohne abgeschlossene Simulation erklärt die Gruppenfrage die Sperre und sendet nicht', async () => {
      const { w } = await mountAt('/simulations/sim_1/interviews', 'running')
      await w.get('[data-testid="group-toggle"]').trigger('click')
      expect(w.get('[data-testid="group-blocked"]').text()).toContain('abgeschlossen')
      await w.get('[data-testid="group-select-all"]').trigger('click')
      await w.get('[data-testid="group-text"]').setValue('Frage')
      expect(w.get('[data-testid="group-send"]').attributes('disabled')).toBeDefined()
      expect(api.askPersonas).not.toHaveBeenCalled()
    })

    it('exportiert die Antworten als CSV mit Spalten, Dateiname und Fehlerspalte', async () => {
      api.askPersonas.mockResolvedValue([
        { agentId: 0, platform: 'reddit', prompt: 'p', response: 'Sagt "ja"\n=1+1', timestamp: '2026-10-07T12:00:00', error: null },
        { agentId: 1, platform: 'reddit', prompt: null, response: null, timestamp: null, error: 'kaputt' },
      ])
      const { w } = await mountAt('/simulations/sim_1/interviews')
      await askAll(w)
      await w.get('[data-testid="group-export-csv"]').trigger('click')
      expect(download.triggerDownload).toHaveBeenCalledTimes(1)
      const [blob, filename] = download.triggerDownload.mock.calls[0] as [Blob, string]
      expect(filename).toMatch(/^agora-survey-\d+\.csv$/)
      expect(blob.type).toBe('text/csv;charset=utf-8')
      const csv = await blob.text()
      expect(csv.split('\n')[0]).toBe('"agent_id","username","question","answer","error"')
      expect(csv).toContain('"0","Anke Wübbena","Frage an alle","Sagt ""ja""\n=1+1",""')
      expect(csv).toContain('"1","Jörg Kreistag","Frage an alle","","kaputt"')
      expect(w.get('[data-testid="group-export-status"]').text()).toBe('CSV mit 2 Zeilen exportiert.')
    })

    it('Budgetabbruch (409): kein CSV-Knopf, Budgethinweis bleibt sichtbar', async () => {
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
      const { w } = await mountAt('/simulations/sim_1/interviews')
      await askAll(w)
      expect(w.get('[data-testid="budget-notice"]').attributes('role')).toBe('alert')
      expect(w.find('[data-testid="group-export-csv"]').exists()).toBe(false)
      expect(w.get('[data-testid="group-export-none"]').text()).toContain('Keine Antwort zum Exportieren')
      expect(download.triggerDownload).not.toHaveBeenCalled()
    })
  })

  it('jedes Formularfeld hat ein echtes <label for>', async () => {
    const { w } = await mountAt('/simulations/sim_1/interviews/persona-0')
    await w.get('[data-testid="group-toggle"]').trigger('click')
    const fields = w.findAll('select, textarea, input')
    expect(fields.length).toBeGreaterThan(0)
    for (const f of fields) {
      const id = f.attributes('id')
      expect(id, f.html()).toBeTruthy()
      expect(w.find(`label[for="${id}"]`).exists(), id).toBe(true)
    }
  })
})
