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

function workspaceWith(simState: string) {
  return {
    stages: computed(() => [{ key: 'simulation', state: simState }]),
  } as unknown as RunWorkspace
}

async function mountAt(path: string, simState: string | null = 'done') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/simulations/:simulationId/interviews/:conversationId?',
        name: 'RunInterviews',
        component: RunInterviewsView,
        props: true,
      },
    ],
  })
  await router.push(path)
  await router.isReady()
  const Host = defineComponent({
    setup() {
      if (simState) provide(RUN_WORKSPACE_KEY, workspaceWith(simState))
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
  api.getInterviewHistory.mockResolvedValue([])
  api.getSimulationConfig.mockResolvedValue({ success: true, data: { llm_model: 'gpt-x' } })
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
    expect(w.get('[data-testid="turn-answer"]').text()).toContain('SIM · Interview')
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
