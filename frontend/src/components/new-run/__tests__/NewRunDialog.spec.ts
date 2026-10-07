/**
 * NewRunDialog — Startdialog „Neuer Lauf“ (#1799, Etappe 3).
 *
 * Prüft die fünf Gruppen, Pflichtfeld Frage, deaktivierte Optionen mit
 * Begründung, schreibgeschützte Frage am vorhandenen Graphen, „Nur anlegen“
 * (nur create), „Starten“ (create, dann prepare, pendingRunParams), Budget nur
 * bei Änderung, „Neu aus Quelle“ (setPendingUpload + Process), Fehlerpfade,
 * Vorbelegung aus den Einstellungen samt Rückfall bei 403 und Schließen.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'

const operator = vi.hoisted(() => ({ value: true }))
vi.mock('@/composables/useOperatorAccess', async () => {
  const { computed } = await import('vue')
  return { useOperatorAccess: () => computed(() => operator.value) }
})
// Ein einziger Mock je Modul. Zwei `@/api/simulation`-Mocks wuerfen sich
// gegenseitig weg — der spaetere gewinnt, und ein im frueheren ergaenztes
// `createSimulationFromPersonas` (#1807) fehlte dann im Aufrufpfad.
vi.mock('@/api/personaSets', async () => {
  const actual = await vi.importActual<typeof import('@/api/personaSets')>('@/api/personaSets')
  return { ...actual, listPersonaSets: api.listPersonaSets }
})
vi.mock('@/api/simulation', async () => {
  const actual = await vi.importActual<typeof import('@/api/simulation')>('@/api/simulation')
  return {
    ...actual,
    createSimulation: api.createSimulation,
    prepareSimulation: api.prepareSimulation,
    createSimulationFromPersonas: api.createSimulationFromPersonas,
    getAvailableModels: api.getAvailableModels,
  }
})
vi.mock('@/composables/useEffectiveModelSelection', () => ({
  useEffectiveModelSelection: () => ({
    effectiveRef: { value: null },
    ensureLoaded: vi.fn().mockResolvedValue(undefined),
  }),
}))

const api = vi.hoisted(() => ({
  listProjects: vi.fn(),
  createSimulation: vi.fn(),
  prepareSimulation: vi.fn(),
  getAvailableModels: vi.fn(),
  fetchLlmProfiles: vi.fn(),
  preflightEstimate: vi.fn(),
  setPendingUpload: vi.fn(),
  ensureLoaded: vi.fn(),
  createSimulationFromPersonas: vi.fn(),
  listPersonaSets: vi.fn(),
}))
const settingsFields = vi.hoisted(() => ({ value: {} as Record<string, unknown[]> }))

vi.mock('@/api/graph', () => ({ listProjects: api.listProjects }))

vi.mock('@/api/llmProfiles', () => ({ fetchLlmProfiles: api.fetchLlmProfiles }))
vi.mock('@/api/budget', () => ({ preflightEstimate: api.preflightEstimate }))
vi.mock('@/store/pendingUpload', () => ({ setPendingUpload: api.setPendingUpload }))
vi.mock('@/store/settings', () => ({
  useSettingsStore: () => ({
    ensureLoaded: api.ensureLoaded,
    get fields() {
      return settingsFields.value
    },
  }),
}))
vi.mock('@/components/v4/forms/AiModelPicker.vue', () => ({
  default: {
    name: 'AiModelPicker',
    props: ['modelValue', 'placeholder', 'mode'],
    emits: ['update:modelValue'],
    template: '<div data-testid="ai-model-picker" />',
  },
}))
vi.mock('@/components/v4/run-budget/RunBudgetForm.vue', () => ({
  default: {
    name: 'RunBudgetForm',
    props: ['modelValue', 'disabled'],
    emits: ['update:modelValue'],
    template:
      '<div data-testid="budget-form" :data-value="JSON.stringify(modelValue)">' +
      '<button type="button" data-testid="budget-edit" @click="$emit(\'update:modelValue\', { schema_version: 1, max_tokens: 5000, enforcement: \'soft\', currency: \'USD\' })" />' +
      '</div>',
  },
}))
vi.mock('@/components/v4/run-budget/PreflightEstimateCard.vue', () => ({
  default: { name: 'PreflightEstimateCard', props: ['estimate', 'loading', 'error'], template: '<div />' },
}))

import NewRunDialog from '../NewRunDialog.vue'
import { PENDING_RUN_PARAMS_PREFIX } from '@/composables/new-run/pendingRunParams'
import { useSettingsWindowStore } from '@/stores/settingsWindow'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })
const stub = { template: '<div />' }

function project(id: string, over: Record<string, unknown> = {}) {
  return {
    project_id: id,
    name: `Graph ${id}`,
    status: 'graph_completed',
    created_at: '2026-10-01T10:00:00Z',
    updated_at: '2026-10-02T10:00:00Z',
    files: [],
    total_text_length: 10,
    ontology: null,
    analysis_summary: null,
    graph_id: `g-${id}`,
    graph_build_task_id: null,
    simulation_requirement: `Frage zu ${id}`,
    chunk_size: 500,
    chunk_overlap: 50,
    llm_model: null,
    llm_provider: null,
    llm_profile_id: null,
    ai_model_ref: null,
    error: null,
    ...over,
  }
}

let wrapper: VueWrapper | null = null

async function mountDialog(path = '/library/runs/new', returnTo: string | null = null) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSettingsWindowStore().open(returnTo)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/library/runs', name: 'LibraryRuns', component: stub },
      { path: '/library/runs/new', name: 'NewRun', component: stub, meta: { windowOverBackground: true } },
      { path: '/simulations/:simulationId', name: 'RunOverview', component: stub },
      { path: '/process/:projectId', name: 'Process', component: stub },
    ],
  })
  await router.push(path)
  await router.isReady()
  wrapper = mount(NewRunDialog, { global: { plugins: [router, pinia, i18n] }, attachTo: document.body })
  await flushPromises()
  await flushPromises()
  return { router }
}

const q = <T extends Element>(sel: string) => document.body.querySelector<T>(sel)
const qa = <T extends Element>(sel: string) => Array.from(document.body.querySelectorAll<T>(sel))
const byTestId = <T extends HTMLElement>(id: string) => q<T>(`[data-testid="${id}"]`)
/** Wie `byTestId`, aber bricht mit einer lesbaren Meldung statt `null`
 *  weiterzureichen — im Personasatz-Block ist sein Fehlen der Befund. */
const need = <T extends HTMLElement>(id: string): T => {
  const el = byTestId<T>(id)
  if (!el) throw new Error(`Element ${id} fehlt`)
  return el
}

async function type(el: HTMLTextAreaElement | HTMLInputElement | null, value: string) {
  if (!el) throw new Error('Feld fehlt')
  el.value = value
  el.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}

async function click(el: HTMLElement | null) {
  if (!el) throw new Error('Element fehlt')
  el.click()
  await flushPromises()
  await flushPromises()
}

async function chooseGraphMode(mode: 'existing' | 'new') {
  const radio = qa<HTMLInputElement>('input[name="graph-mode"]').find((r) => r.value === mode)
  if (!radio) throw new Error('Radio fehlt')
  radio.checked = true
  radio.dispatchEvent(new Event('change', { bubbles: true }))
  await flushPromises()
}

async function addFile(name = 'quelle.md') {
  const input = byTestId<HTMLInputElement>('new-run-file-input')
  const file = new File(['Inhalt'], name, { type: 'text/markdown' })
  Object.defineProperty(input, 'files', { value: [file], configurable: true })
  input?.dispatchEvent(new Event('change', { bubbles: true }))
  await flushPromises()
  return file
}

const startBtn = () => byTestId<HTMLButtonElement>('new-run-start')
const createBtn = () => byTestId<HTMLButtonElement>('new-run-create-only')

beforeEach(() => {
  document.body.innerHTML = ''
  window.sessionStorage.clear()
  window.localStorage.clear()
  operator.value = true
  settingsFields.value = {}
  Object.values(api).forEach((m) => m.mockReset())
  api.listProjects.mockResolvedValue({ success: true, data: [project('p1'), project('p2', { status: 'created', graph_id: null })] })
  api.getAvailableModels.mockResolvedValue({ success: true, data: { neo4j_reachable: true, default_language: 'de' } })
  api.fetchLlmProfiles.mockResolvedValue([])
  api.ensureLoaded.mockResolvedValue(undefined)
  api.createSimulation.mockResolvedValue({ success: true, data: { simulation_id: 'sim-1', project_id: 'p1', status: 'created' } })
  api.prepareSimulation.mockResolvedValue({ success: true, data: { task_id: 't1' } })
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
})

describe('NewRunDialog — Aufbau', () => {
  it('rendert Dialog und die fünf Gruppen als fieldset/legend', async () => {
    await mountDialog()
    const dialog = q('[role="dialog"]')
    expect(dialog).not.toBeNull()
    const labelled = dialog?.getAttribute('aria-labelledby')
    expect(labelled && document.getElementById(labelled)?.textContent).toBe('Neuer Lauf')
    const legends = qa('.nr__group > legend').map((l) => l.textContent?.trim())
    expect(legends).toEqual(['Frage', 'Graph', 'Personasatz', 'Modelle', 'Umfang und Budget'])
  })

  it('deaktivierte Optionen tragen ihre Begründung per aria-describedby', async () => {
    await mountDialog()
    const none = qa<HTMLInputElement>('input[name="graph-mode"]').find((r) => r.value === 'none')
    expect(none?.disabled).toBe(true)
    const why = document.getElementById(none?.getAttribute('aria-describedby') ?? '')
    expect(why?.textContent).toContain('Noch nicht verfügbar. Simulation und Interviews wären möglich, ein Bericht nicht.')
  })

  it('wählt einen Personasatz aus der Bibliothek (#1807)', async () => {
    // Vor Etappe 7 stand hier ein dauerhaft deaktiviertes Feld mit dem Hinweis,
    // der Satz komme spaeter. Er ist jetzt eine echte Auswahl; der Test haelt
    // fest, dass die Begruendung erhalten bleibt und nicht mehr „kommt spaeter"
    // lautet — sonst waere die Aenderung nicht sichtbar.
    await mountDialog()
    const fromSet = qa<HTMLInputElement>('input[name="persona-mode"]').find((r) => r.value === 'set')

    expect(fromSet?.disabled).toBe(false)
    const why = document.getElementById(fromSet?.getAttribute('aria-describedby') ?? '')
    expect(why?.textContent).toContain('Kopie')
    expect(why?.textContent).not.toContain('Kommt mit')
  })

  describe('Personasatz wählen (#1807)', () => {
    const set = (id: string, name: string, entry_count: number) => ({
      id, name, description: '', graph_id: null, project_id: null,
      entry_count, locked: false, locked_at: null, usage_count: 0,
      created_at: '2026-10-07T10:00:00', updated_at: '2026-10-07T10:00:00', schema_version: 1 as const,
    })

    beforeEach(() => {
      api.listPersonaSets.mockResolvedValue({
        count: 2,
        sets: [set('pset_a', 'Betroffene', 12), set('pset_b', 'Leere', 0)],
      })
    })

    it('zeigt die Auswahl erst nach dem Wählen der Option', async () => {
      await mountDialog()
      expect(byTestId('new-run-persona-set')).toBeNull()

      await qa<HTMLInputElement>('input[name="persona-mode"]')
        .find((r) => r.value === 'set')!.click()
      await flushPromises()

      expect(byTestId('new-run-persona-set')).not.toBeNull()
    })

    it('bietet nur Saetze mit Personas an', async () => {
      // Ein leerer Satz kann keinen Lauf tragen; ihn anzubieten wuerde einen
      // Fehler des Servers vorwegnehmen, den der Dialog selbst vermeiden kann.
      await mountDialog()
      await qa<HTMLInputElement>('input[name="persona-mode"]')
        .find((r) => r.value === 'set')!.click()
      await flushPromises()

      const options = Array.from(need<HTMLSelectElement>('new-run-persona-set').options)
        .map((o) => o.value)
        .filter(Boolean)
      expect(options).toEqual(['pset_a'])
    })

    it('sagt, wenn es keinen brauchbaren Satz gibt', async () => {
      api.listPersonaSets.mockResolvedValue({ count: 1, sets: [set('pset_b', 'Leere', 0)] })
      await mountDialog()
      await qa<HTMLInputElement>('input[name="persona-mode"]')
        .find((r) => r.value === 'set')!.click()
      await flushPromises()

      const text = need<HTMLSelectElement>('new-run-persona-set').closest('div')?.textContent ?? ''
      expect(text).toContain('Es gibt noch keinen Satz mit Personas')
    })

    it('nennt den Leerzustand des Graphen, statt ihn zu verschweigen', async () => {
      // Der Satz-Weg laeuft ohne Graph. Wer das nicht sieht, wartet im Lauf auf
      // einen Graphen, den es nicht geben wird.
      await mountDialog()
      await qa<HTMLInputElement>('input[name="persona-mode"]')
        .find((r) => r.value === 'set')!.click()
      await flushPromises()
      const picker = need<HTMLSelectElement>('new-run-persona-set')
      picker.value = 'pset_a'
      await picker.dispatchEvent(new Event('change'))
      await flushPromises()

      expect(picker.closest('div')?.textContent).toContain('ohne Graph')
    })

    it('„Starten“ legt den Lauf über create-from-personas an, ohne prepare', async () => {
      api.createSimulationFromPersonas.mockResolvedValue({
        success: true,
        data: { simulation_id: 'sim-9', project_id: 'proj-9', persona_count: 12 },
      })
      const { router } = await mountDialog()
      await type(need<HTMLTextAreaElement>('new-run-question'), 'Wie hält das Betriebsrat?')
      await qa<HTMLInputElement>('input[name="persona-mode"]').find((r) => r.value === 'set')!.click()
      await flushPromises()
      const picker = need<HTMLSelectElement>('new-run-persona-set')
      picker.value = 'pset_a'
      await picker.dispatchEvent(new Event('change'))
      await flushPromises()
      await click(startBtn())
      await flushPromises()

      expect(api.createSimulationFromPersonas).toHaveBeenCalledWith({
        simulation_requirement: 'Wie hält das Betriebsrat?',
        persona_set_id: 'pset_a',
      })
      // Der Weg traegt weder Datei noch Graph und bereitet nicht nach: der
      // Endpunkt macht beides in einem Schritt.
      expect(api.createSimulation).not.toHaveBeenCalled()
      expect(api.prepareSimulation).not.toHaveBeenCalled()
      expect(router.currentRoute.value.name).toBe('RunOverview')
    })

    it('verlangt die Frage auch ohne Graph', async () => {
      // Der Endpunkt braucht `simulation_requirement`, auch ohne Graph. Ohne
      // diese Forderung ginge ein Lauf ohne Fragestellung raus und der Server
      // wuerde ihn mit 400 ablehnen. Geprueft wird der Blocker, nicht die
      // Frage selbst: die ist im Satz-Weg Pflicht wie im Graph-Weg.
      await mountDialog()
      await qa<HTMLInputElement>('input[name="persona-mode"]')
        .find((r) => r.value === 'set')!.click()
      await flushPromises()

      // Ohne Satz gewaehlt: der Satz-Blocker steht da.
      expect(document.body.textContent).toContain('Bitte einen Personasatz wählen')

      const picker = need<HTMLSelectElement>('new-run-persona-set')
      picker.value = 'pset_a'
      await picker.dispatchEvent(new Event('change'))
      await flushPromises()

      // Mit Satz, aber ohne Frage: jetzt der Frage-Blocker.
      const text = document.body.textContent ?? ''
      expect(text).not.toContain('Bitte einen Personasatz wählen')
      expect(text).toContain('Die Simulationsfrage fehlt.')
      // Der Startknopf bleibt gesperrt.
      expect(need<HTMLButtonElement>('new-run-start').disabled).toBe(true)
    })
  })

  it('zeigt Modell-Hinweis, kein Feld „Anzahl“ und keinen Je-Stufe-Teil', async () => {
    await mountDialog()
    expect(q('.nr')?.textContent).toContain(
      'Gilt für alle Stufen dieses Laufs. Abweichungen je Stufe wählst du am Startknopf der Stufe.',
    )
    expect(qa('label').filter((l) => l.textContent?.trim() === 'Anzahl')).toHaveLength(0)
    expect(q('details')).toBeNull()
  })

  it('bietet nur Graphen mit status graph_completed an', async () => {
    await mountDialog()
    await chooseGraphMode('existing')
    const options = qa<HTMLOptionElement>('[data-testid="new-run-graph-select"] option')
    expect(options.map((o) => o.value)).toEqual(['p1'])
  })
})

describe('NewRunDialog — Frage', () => {
  it('Pflichtfeld Frage: ohne Frage bleibt „Graph bauen“ gesperrt und nennt den Grund', async () => {
    await mountDialog()
    await addFile()
    expect(startBtn()?.textContent?.trim()).toBe('Graph bauen')
    expect(startBtn()?.disabled).toBe(true)
    expect(byTestId('new-run-blockers')?.textContent).toContain('Die Simulationsfrage fehlt.')
    await type(need<HTMLTextAreaElement>('new-run-question'), 'Wie reagiert der Rat?')
    expect(startBtn()?.disabled).toBe(false)
  })

  it('vorhandener Graph zeigt dessen Frage schreibgeschützt mit Hinweis', async () => {
    await mountDialog()
    await chooseGraphMode('existing')
    const field = need<HTMLTextAreaElement>('new-run-question')
    expect(field?.readOnly).toBe(true)
    expect(field?.value).toBe('Frage zu p1')
    expect(q('.nr')?.textContent).toContain(
      'Die Frage gehört zum Graphen. Für eine andere Frage einen neuen Graphen aus der Quelle bauen.',
    )
  })

  it('Vorwahl über ?graph=<projectId> wählt den Graphen', async () => {
    await mountDialog('/library/runs/new?graph=p1')
    expect(qa<HTMLInputElement>('input[name="graph-mode"]').find((r) => r.value === 'existing')?.checked).toBe(true)
    expect(byTestId<HTMLSelectElement>('new-run-graph-select')?.value).toBe('p1')
  })
})

describe('NewRunDialog — vorhandener Graph', () => {
  it('„Nur anlegen“ ruft nur create und führt zur Übersicht', async () => {
    const { router } = await mountDialog('/library/runs/new?graph=p1')
    await click(createBtn())
    expect(api.createSimulation).toHaveBeenCalledWith({
      project_id: 'p1',
      graph_id: 'g-p1',
      enable_twitter: true,
      enable_reddit: true,
    })
    expect(api.prepareSimulation).not.toHaveBeenCalled()
    expect(router.currentRoute.value.name).toBe('RunOverview')
    expect(router.currentRoute.value.params.simulationId).toBe('sim-1')
  })

  it('„Starten“ ruft create, dann prepare, und merkt Tage, Runden und Budget vor', async () => {
    const { router } = await mountDialog('/library/runs/new?graph=p1')
    await type(qa<HTMLTextAreaElement>('textarea').find((t) => t.minLength === 10) ?? null, 'Wer blockiert die Reform?')
    await click(byTestId('budget-edit'))
    await click(startBtn())
    expect(api.createSimulation).toHaveBeenCalledTimes(1)
    expect(api.prepareSimulation).toHaveBeenCalledTimes(1)
    expect(api.createSimulation.mock.invocationCallOrder[0]).toBeLessThan(api.prepareSimulation.mock.invocationCallOrder[0] ?? 0)
    expect(api.prepareSimulation).toHaveBeenCalledWith({
      simulation_id: 'sim-1',
      use_llm_for_profiles: true,
      language: 'de',
      activity_mode: 'realistic',
      max_agents: 30,
      contested_question: 'Wer blockiert die Reform?',
      budget: { schema_version: 1, max_tokens: 5000, enforcement: 'soft', currency: 'USD' },
    })
    const stored = JSON.parse(window.sessionStorage.getItem(`${PENDING_RUN_PARAMS_PREFIX}sim-1`) ?? 'null')
    expect(stored).toEqual({
      maxRounds: 24,
      simulationDays: 1,
      budget: { schema_version: 1, max_tokens: 5000, enforcement: 'soft', currency: 'USD' },
    })
    expect(router.currentRoute.value.name).toBe('RunOverview')
  })

  it('sendet ein Profil als llm_profile_id', async () => {
    api.fetchLlmProfiles.mockResolvedValue([
      {
        id: 'abc', name: 'Profil', provider: 'openai', base_url: 'x', model_name: 'gpt', api_key: '',
        is_default: false, created_at: 'x', updated_at: 'x',
      },
    ])
    await mountDialog('/library/runs/new?graph=p1')
    const select = byTestId<HTMLSelectElement>('new-run-profile')
    if (!select) throw new Error('Profilauswahl fehlt')
    select.value = 'abc'
    select.dispatchEvent(new Event('change', { bubbles: true }))
    await flushPromises()
    await click(startBtn())
    expect(api.prepareSimulation.mock.calls[0]?.[0]).toMatchObject({ llm_profile_id: 'abc' })
    expect(api.prepareSimulation.mock.calls[0]?.[0]).not.toHaveProperty('ai_model_ref')
  })

  it('unverändertes Budget wird nicht gesendet, geändertes schon', async () => {
    settingsFields.value = {
      budget: [
        { key: 'AGORA_SIM_DEFAULT_MAX_TOKENS', value: 20000000 },
        { key: 'AGORA_SIM_DEFAULT_MAX_COST_MICROS', value: 0 },
        { key: 'AGORA_SIM_DEFAULT_MAX_DURATION_SECONDS', value: 0 },
        { key: 'AGORA_SIM_DEFAULT_MAX_LLM_CALLS', value: 0 },
        { key: 'AGORA_SIM_DEFAULT_BUDGET_ENFORCEMENT', value: 'hard' },
      ],
    }
    await mountDialog('/library/runs/new?graph=p1')
    // Vorbelegung: 0 wird weggelassen.
    expect(JSON.parse(byTestId('budget-form')?.getAttribute('data-value') ?? 'null')).toEqual({
      schema_version: 1,
      max_tokens: 20000000,
      enforcement: 'hard',
      currency: 'USD',
    })
    expect(q('.nr')?.textContent).not.toContain('Ein eigenes Budget ersetzt die Standardgrenzen vollständig.')
    await click(startBtn())
    expect(api.prepareSimulation.mock.calls[0]?.[0]).not.toHaveProperty('budget')
    expect(JSON.parse(window.sessionStorage.getItem(`${PENDING_RUN_PARAMS_PREFIX}sim-1`) ?? 'null').budget).toBeNull()
  })

  it('geändertes Budget nennt, dass es die Standardgrenzen ersetzt', async () => {
    settingsFields.value = { budget: [{ key: 'AGORA_SIM_DEFAULT_MAX_TOKENS', value: 20000000 }] }
    await mountDialog('/library/runs/new?graph=p1')
    await click(byTestId('budget-edit'))
    expect(byTestId('new-run-budget-replaces')?.textContent).toContain(
      'Ein eigenes Budget ersetzt die Standardgrenzen vollständig.',
    )
    await click(startBtn())
    expect(api.prepareSimulation.mock.calls[0]?.[0]).toHaveProperty('budget.max_tokens', 5000)
  })

  it('Rückfall bei gesperrten Einstellungen: leeres Formular und Hinweis auf die Instanzgrenzen', async () => {
    api.ensureLoaded.mockRejectedValue(new Error('403'))
    await mountDialog('/library/runs/new?graph=p1')
    expect(byTestId('new-run-budget-unavailable')?.textContent).toContain(
      'Es gelten die Standardgrenzen der Instanz.',
    )
    expect(byTestId('budget-form')?.getAttribute('data-value')).toBe('null')
    await click(startBtn())
    expect(api.prepareSimulation.mock.calls[0]?.[0]).not.toHaveProperty('budget')
  })

  it('Obergrenze der Personas: mindestens 10', async () => {
    await mountDialog('/library/runs/new?graph=p1')
    const number = qa<HTMLInputElement>('input.agent-cap-number')[0]
    await type(number ?? null, '5')
    expect(startBtn()?.disabled).toBe(true)
    expect(byTestId('new-run-blockers')?.textContent).toContain('mindestens 10')
  })
})

describe('NewRunDialog — neu aus Quelle', () => {
  it('„Starten“ nutzt setPendingUpload und geht nach Process mit Run-Query', async () => {
    const { router } = await mountDialog()
    const file = await addFile('quelle.md')
    await type(need<HTMLTextAreaElement>('new-run-question'), 'Wie reagiert der Rat?')
    await click(startBtn())
    expect(api.setPendingUpload).toHaveBeenCalledWith(
      [file],
      'Wie reagiert der Rat?',
      null,
      30,
      24,
      ['domain_fact'],
    )
    expect(api.createSimulation).not.toHaveBeenCalled()
    expect(router.currentRoute.value.name).toBe('Process')
    expect(router.currentRoute.value.params.projectId).toBe('new')
    expect(router.currentRoute.value.query).toEqual({ maxRounds: '24', simulationDays: '1' })
  })

  it('„Nur anlegen“ ist gesperrt und nennt den Grund', async () => {
    await mountDialog()
    await addFile()
    await type(need<HTMLTextAreaElement>('new-run-question'), 'Frage?')
    expect(createBtn()?.disabled).toBe(true)
    const why = document.getElementById(createBtn()?.getAttribute('aria-describedby') ?? '')
    expect(why?.textContent).toContain('Ein Lauf entsteht, sobald der Graph gebaut ist.')
  })
})

describe('NewRunDialog — Voraussetzungen und Fehler', () => {
  it('Neo4j nicht erreichbar: sichtbarer Hinweis statt nur gesperrtem Knopf', async () => {
    api.getAvailableModels.mockResolvedValue({ success: true, data: { neo4j_reachable: false } })
    await mountDialog('/library/runs/new?graph=p1')
    expect(startBtn()?.disabled).toBe(true)
    expect(byTestId('new-run-blockers')?.textContent).toContain('Neo4j-Bereitschaft noch nicht bestätigt')
  })

  it('Nicht-Betreiber braucht eine ausdrückliche Modellwahl', async () => {
    operator.value = false
    await mountDialog('/library/runs/new?graph=p1')
    expect(byTestId('new-run-profile')).toBeNull()
    expect(startBtn()?.disabled).toBe(true)
    wrapper?.findComponent({ name: 'AiModelPicker' }).vm.$emit('update:modelValue', {
      provider_connection_id: 'google',
      model_id: 'gemini',
      source: 'explicit',
    })
    await flushPromises()
    expect(startBtn()?.disabled).toBe(false)
    await click(startBtn())
    expect(api.prepareSimulation.mock.calls[0]?.[0]).toMatchObject({
      ai_model_ref: { provider_connection_id: 'google', model_id: 'gemini', source: 'explicit' },
    })
  })

  it('create schlägt fehl: Fehler im Dialog, Eingaben bleiben, kein prepare', async () => {
    api.createSimulation.mockResolvedValue({ success: false, error: 'Budget überschritten' })
    const { router } = await mountDialog('/library/runs/new?graph=p1')
    await type(qa<HTMLTextAreaElement>('textarea').find((t) => t.minLength === 10) ?? null, 'Eine lange Streitfrage')
    await click(startBtn())
    expect(byTestId('new-run-error')?.textContent).toContain('Budget überschritten')
    expect(api.prepareSimulation).not.toHaveBeenCalled()
    expect(router.currentRoute.value.name).toBe('NewRun')
    expect(qa<HTMLTextAreaElement>('textarea').find((t) => t.minLength === 10)?.value).toBe('Eine lange Streitfrage')
    expect(startBtn()?.disabled).toBe(false)
  })

  it('create wirft (HTTP 5xx): Meldung des Fehlers wird angezeigt', async () => {
    api.createSimulation.mockRejectedValue(new Error('HTTP 503'))
    await mountDialog('/library/runs/new?graph=p1')
    await click(startBtn())
    expect(byTestId('new-run-error')?.textContent).toContain('HTTP 503')
  })

  it('prepare schlägt nach create fehl: Lauf wird genannt, Link zum Lauf, Wiederholung legt nichts neu an', async () => {
    api.prepareSimulation.mockRejectedValueOnce(new Error('Rate-Limit des Anbieters'))
    const { router } = await mountDialog('/library/runs/new?graph=p1')
    await click(startBtn())
    const text = byTestId('new-run-error')?.textContent ?? ''
    expect(text).toContain('sim-1')
    expect(text).toContain('Rate-Limit des Anbieters')
    expect(byTestId('new-run-created-link')).not.toBeNull()
    expect(router.currentRoute.value.name).toBe('NewRun')
    expect(window.sessionStorage.getItem(`${PENDING_RUN_PARAMS_PREFIX}sim-1`)).toBeNull()

    await click(startBtn())
    expect(api.createSimulation).toHaveBeenCalledTimes(1)
    expect(api.prepareSimulation).toHaveBeenCalledTimes(2)
    expect(router.currentRoute.value.name).toBe('RunOverview')
  })

  it('während des Aufrufs: Fortschritt sichtbar und Knöpfe gesperrt', async () => {
    let resolve: (v: unknown) => void = () => undefined
    api.createSimulation.mockReturnValue(new Promise((r) => { resolve = r }))
    await mountDialog('/library/runs/new?graph=p1')
    startBtn()?.click()
    await flushPromises()
    expect(byTestId('new-run-progress')?.textContent).toContain('Der Lauf wird angelegt')
    expect(startBtn()?.disabled).toBe(true)
    expect(createBtn()?.disabled).toBe(true)
    resolve({ success: true, data: { simulation_id: 'sim-1' } })
    await flushPromises()
  })

  it('unlesbare create-Antwort wird als Fehler gemeldet', async () => {
    api.createSimulation.mockResolvedValue({ success: true, data: { foo: 1 } })
    await mountDialog('/library/runs/new?graph=p1')
    await click(startBtn())
    expect(byTestId('new-run-error')?.textContent).toContain('unvollständig')
    expect(api.prepareSimulation).not.toHaveBeenCalled()
  })
})

describe('NewRunDialog — Schließen', () => {
  it('Schließen führt zur gemerkten Ansicht', async () => {
    const { router } = await mountDialog('/library/runs/new', '/library/runs')
    await click(q<HTMLButtonElement>('.nr__close'))
    expect(router.currentRoute.value.path).toBe('/library/runs')
  })

  it('Esc schließt den Dialog', async () => {
    const { router } = await mountDialog()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/library/runs')
  })

  it('Fokus kehrt zum Auslöser zurück', async () => {
    const trigger = document.createElement('button')
    document.body.appendChild(trigger)
    trigger.focus()
    expect(document.activeElement).toBe(trigger)
    await mountDialog()
    wrapper?.unmount()
    wrapper = null
    await flushPromises()
    await new Promise((r) => setTimeout(r, 10))
    expect(document.activeElement).toBe(trigger)
  })
})
