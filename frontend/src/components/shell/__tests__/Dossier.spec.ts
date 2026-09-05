/**
 * Dossier — Komponenten-Tests (Block B3).
 *
 * Prueft:
 * 1. Ohne Objekt erscheint der Leer-Hinweis (shelf.dossier.emptyHint).
 * 2. Mit Objekt: Titel, Zusammenfassung und KPIs (metaId) werden angezeigt.
 * 3. Abbrechen-Knopf nur bei aktivem Objekt.
 * 4. Pause-Knopf nur bei pausierbarer aktiver Simulation, ruft pauseSimulation.
 * 5. Abbrechen ruft useCancelAction.cancel() mit der richtigen runId auf.
 * 6. Weiter-Knopf (Weiter-Aktion) nur bei vorhandener nextAction, navigiert dorthin.
 *
 * Selektoren ausschliesslich ueber DossierTestId (src/contracts/testIds.ts).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { computed, ref } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { DossierTestId } from '../../../contracts/testIds'
import type { ShelfFilter, ShelfJobRow, ShelfObject } from '../../../types/shelf'
import type { useShelf } from '../../../composables/useShelf'

vi.mock('../../../api/runs', () => ({
  cancelRun: vi.fn().mockResolvedValue({ success: true }),
}))
vi.mock('../../../api/simulation', () => ({
  pauseSimulation: vi.fn().mockResolvedValue({}),
  resumeSimulation: vi.fn().mockResolvedValue({}),
  createSimulationBranch: vi.fn(),
  createSimulationFromPersonas: vi.fn(),
  listPersonaTemplates: vi.fn().mockResolvedValue({ success: true, data: { count: 0, templates: [] } }),
}))
vi.mock('../../../api/status', () => ({
  getSystemStatus: vi.fn().mockResolvedValue({ success: true }),
}))
vi.mock('../../../api/report', () => ({
  getReport: vi.fn().mockResolvedValue({ success: false }),
  getReportEvidence: vi.fn().mockResolvedValue({ success: false }),
}))

import { pauseSimulation, resumeSimulation, createSimulationBranch, createSimulationFromPersonas } from '../../../api/simulation'
import { getReport, getReportEvidence } from '../../../api/report'
import { useCancelAction } from '../useCancelAction'
import Dossier from '../Dossier.vue'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/runs/:id', name: 'RunDetail', component: { template: '<div/>' } },
    { path: '/v4/env-setup/:projectId', name: 'StepEnvSetup', component: { template: '<div/>' } },
    { path: '/v4/report/:reportId', name: 'StepReport', component: { template: '<div/>' } },
    { path: '/ablage/:kind/:objectId', name: 'ShelfObject', component: { template: '<div/>' } },
    { path: '/dashboard', name: 'Dashboard', component: { template: '<div/>' } },
    { path: '/settings', name: 'SettingsGeneral', component: { template: '<div/>' } },
  ],
})

function makeObject(overrides: Partial<ShelfObject> = {}): ShelfObject {
  return {
    kind: 'lauf',
    id: 'sim_1',
    title: 'Testlauf eins',
    statusLine: 'Laeuft',
    updatedAt: '2026-08-18T10:00:00Z',
    metaId: 'sim_1',
    nextAction: null,
    active: null,
    ...overrides,
  }
}

/** Baut ein Objekt, das dieselbe Form wie ReturnType<typeof useShelf> hat, ohne die echten API-Aufrufe zu machen. */
function makeShelf(objects: ShelfObject[] = []): ReturnType<typeof useShelf> {
  const objectsRef = ref<ShelfObject[]>(objects)
  const filter = ref<ShelfFilter>('alle')
  const loading = ref(false)
  const error = ref('')
  const filtered = computed(() =>
    filter.value === 'alle' || filter.value === 'jobs' ? objectsRef.value : objectsRef.value.filter((o) => o.kind === filter.value),
  )
  const counts = computed(() => {
    const c: Record<string, number> = { alle: objectsRef.value.length, lauf: 0, bericht: 0, personasatz: 0, graph: 0 }
    for (const o of objectsRef.value) c[o.kind] += 1
    return c
  })
  const activeObjects = computed(() => objectsRef.value.filter((o) => o.active !== null))
  return {
    objects: objectsRef,
    jobs: ref<ShelfJobRow[]>([]),
    filter,
    filtered,
    counts,
    activeObjects,
    loading,
    error,
    reload: vi.fn().mockResolvedValue(undefined),
  }
}

function mountDossier(object: ShelfObject | null, shelfObjects: ShelfObject[] = object ? [object] : []) {
  return mount(Dossier, {
    props: { object, shelf: makeShelf(shelfObjects) },
    global: { plugins: [i18n, router] },
  })
}

describe('Dossier', () => {
  beforeEach(() => {
    useCancelAction().undo()
  })

  it('ohne Objekt erscheint die Uebersicht (Redesign PR 3)', () => {
    const wrapper = mountDossier(null, [])
    expect(wrapper.find(`[data-testid="${DossierTestId.overview}"]`).exists()).toBe(true)
    expect(wrapper.find(`[data-testid="${DossierTestId.root}"]`).text()).toContain(
      'Wähle links ein Objekt, um sein Dossier zu öffnen.',
    )
    expect(wrapper.find(`[data-testid="${DossierTestId.title}"]`).exists()).toBe(false)
  })

  it('mit Objekt zeigt Titel, Zusammenfassung und Meta-ID in den KPIs', () => {
    const obj = makeObject({ title: 'Mein Lauf', statusLine: 'Simulation pausiert · Runde 12/20', metaId: 'sim_xyz' })
    const wrapper = mountDossier(obj)

    expect(wrapper.find(`[data-testid="${DossierTestId.title}"]`).text()).toBe('Mein Lauf')
    expect(wrapper.find(`[data-testid="${DossierTestId.summary}"]`).text()).toBe('Simulation pausiert · Runde 12/20')
    expect(wrapper.find(`[data-testid="${DossierTestId.kpis}"]`).text()).toContain('sim_xyz')
  })

  it('Abbrechen-Knopf nur bei aktivem Objekt', () => {
    const active = makeObject({ active: { runId: 'run_a', status: 'processing', pausable: false, simulationId: null, progress: null } })
    const inactive = makeObject({ active: null })

    expect(mountDossier(active).find(`[data-testid="${DossierTestId.cancel}"]`).exists()).toBe(true)
    expect(mountDossier(inactive).find(`[data-testid="${DossierTestId.cancel}"]`).exists()).toBe(false)
  })

  it('Pause-Knopf nur bei pausierbarer aktiver Simulation, ruft pauseSimulation', async () => {
    const obj = makeObject({ active: { runId: 'run_a', status: 'processing', pausable: true, simulationId: 'sim_a', progress: null } })
    const wrapper = mountDossier(obj)

    await wrapper.find(`[data-testid="${DossierTestId.pause}"]`).trigger('click')
    expect(pauseSimulation).toHaveBeenCalledWith('sim_a')
    expect(resumeSimulation).not.toHaveBeenCalled()
  })

  it('Abbrechen ruft useCancelAction.cancel() mit der richtigen runId auf', async () => {
    const obj = makeObject({ active: { runId: 'run_xyz', status: 'processing', pausable: false, simulationId: null, progress: null } })
    const wrapper = mountDossier(obj)
    const cancelAction = useCancelAction()

    await wrapper.find(`[data-testid="${DossierTestId.cancel}"]`).trigger('click')

    expect(cancelAction.pending.value?.runId).toBe('run_xyz')
  })

  it('Weiter-Knopf nur bei vorhandener Weiter-Aktion, navigiert zum Routenziel', async () => {
    const withAction = makeObject({ nextAction: { label: 'Weiter', to: { name: 'RunDetail', params: { id: 'run_1' } }, kind: 'accent' } })
    const withoutAction = makeObject({ nextAction: null })

    expect(mountDossier(withoutAction).find(`[data-testid="${DossierTestId.openFull}"]`).exists()).toBe(false)

    const wrapper = mountDossier(withAction)
    await wrapper.find(`[data-testid="${DossierTestId.openFull}"]`).trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('RunDetail')
    expect(router.currentRoute.value.params.id).toBe('run_1')
  })
})

describe('Dossier — Lauf aus einem Bericht ableiten (Block B4)', () => {
  it('bietet das Ableiten nur beim Bericht mit bekannter Simulation an', () => {
    const ohne = mountDossier(makeObject({ kind: 'bericht', simulationId: null }))
    expect(ohne.find(`[data-testid="${DossierTestId.derive}"]`).exists()).toBe(false)

    const lauf = mountDossier(makeObject({ kind: 'lauf', simulationId: 'sim_1' }))
    expect(lauf.find(`[data-testid="${DossierTestId.derive}"]`).exists()).toBe(false)

    const bericht = mountDossier(makeObject({ kind: 'bericht', simulationId: 'sim_1' }))
    expect(bericht.find(`[data-testid="${DossierTestId.derive}"]`).exists()).toBe(true)
  })

  it('leitet ab und fuehrt zum neuen Lauf', async () => {
    vi.mocked(createSimulationBranch).mockResolvedValue({
      success: true,
      data: { simulation_id: 'sim_neu' },
    } as never)

    const w = mountDossier(makeObject({ kind: 'bericht', simulationId: 'sim_alt' }))
    await w.find(`[data-testid="${DossierTestId.derive}"]`).trigger('click')
    await flushPromises()

    expect(createSimulationBranch).toHaveBeenCalledWith(
      'sim_alt',
      expect.objectContaining({ copy_profiles: true, copy_report_artifacts: false }),
    )
    expect(router.currentRoute.value.name).toBe('StepEnvSetup')
    expect(router.currentRoute.value.params.projectId).toBe('sim_neu')
  })

  it('sagt es, wenn das Ableiten scheitert, statt still nichts zu tun', async () => {
    vi.mocked(createSimulationBranch).mockRejectedValue(new Error('kaputt'))

    const w = mountDossier(makeObject({ kind: 'bericht', simulationId: 'sim_alt' }))
    await w.find(`[data-testid="${DossierTestId.derive}"]`).trigger('click')
    await flushPromises()

    expect(w.find('[role="alert"]').exists()).toBe(true)
  })
})

describe('Dossier — Lauf aus einem Personasatz starten (Block B4)', () => {
  it('bietet den Start nur beim Personasatz an', () => {
    const bericht = mountDossier(makeObject({ kind: 'bericht', simulationId: 'sim_1' }))
    expect(bericht.find(`[data-testid="${DossierTestId.startFromPersona}"]`).exists()).toBe(false)

    const satz = mountDossier(makeObject({ kind: 'personasatz', id: 'tpl_1' }))
    expect(satz.find(`[data-testid="${DossierTestId.startFromPersona}"]`).exists()).toBe(true)
  })

  it('legt den Lauf mit genau diesem Satz an und fuehrt hin', async () => {
    vi.mocked(createSimulationFromPersonas).mockResolvedValue({
      success: true,
      data: { simulation_id: 'sim_neu', project_id: 'proj_neu', persona_count: 1 },
    } as never)

    const w = mountDossier(makeObject({ kind: 'personasatz', id: 'tpl_1', title: 'Sachbearbeiterin' }))
    await w.find(`[data-testid="${DossierTestId.startFromPersona}"]`).trigger('click')
    await flushPromises()

    expect(createSimulationFromPersonas).toHaveBeenCalledWith(
      expect.objectContaining({ template_ids: ['tpl_1'] }),
    )
    expect(router.currentRoute.value.name).toBe('StepEnvSetup')
    expect(router.currentRoute.value.params.projectId).toBe('sim_neu')
  })

  it('meldet einen Fehlschlag sichtbar', async () => {
    vi.mocked(createSimulationFromPersonas).mockRejectedValue(new Error('kaputt'))

    const w = mountDossier(makeObject({ kind: 'personasatz', id: 'tpl_1' }))
    await w.find(`[data-testid="${DossierTestId.startFromPersona}"]`).trigger('click')
    await flushPromises()

    expect(w.find('[role="alert"]').exists()).toBe(true)
  })
})

describe('Dossier — Uebersichtszustand (Redesign PR 3)', () => {
  it('zeigt ein Objekt mit nextAction.kind=warn unter "Braucht dich" und navigiert ueber dessen Weiter-Aktion', async () => {
    const warnObj = makeObject({
      kind: 'personasatz',
      id: 'tpl_warn',
      title: 'SchulKI',
      statusLine: 'Ungeprueft',
      nextAction: { label: 'Personas freigeben', to: { name: 'StepEnvSetup', params: { projectId: 'proj_1' } }, kind: 'warn' },
    })
    const wrapper = mountDossier(null, [warnObj])

    const item = wrapper.find(`[data-testid="${DossierTestId.overviewAttentionItem}"]`)
    expect(item.exists()).toBe(true)
    expect(item.text()).toContain('SchulKI')

    await item.find('button').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('StepEnvSetup')
    expect(router.currentRoute.value.params.projectId).toBe('proj_1')
  })

  it('zeigt ein aktives Objekt unter "Laeuft gerade" mit Fortschrittsbalken und Abbrechen-Knopf', () => {
    const liveObj = makeObject({
      id: 'sim_live',
      title: 'Domain-Migration',
      active: { runId: 'run_live', status: 'processing', pausable: true, simulationId: 'sim_live', progress: 60 },
    })
    const wrapper = mountDossier(null, [liveObj])

    const card = wrapper.find(`[data-testid="${DossierTestId.overviewLiveItem}"]`)
    expect(card.exists()).toBe(true)
    expect(card.text()).toContain('Domain-Migration')
    expect(card.find('.dossier__ov-bar i').attributes('style')).toContain('60%')
  })

  it('"Zuletzt fertig"-Zeile navigiert zur ShelfObject-Route des Objekts', async () => {
    const doneObj = makeObject({ kind: 'bericht', id: 'rep_1', title: 'Fertiger Bericht', nextAction: null })
    const wrapper = mountDossier(null, [doneObj])

    await wrapper.find(`[data-testid="${DossierTestId.overviewRecentItem}"]`).trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('ShelfObject')
    expect(router.currentRoute.value.params).toEqual({ kind: 'bericht', objectId: 'rep_1' })
  })

  it('"Quelle ablegen" navigiert zum Dashboard', async () => {
    const wrapper = mountDossier(null, [])

    await wrapper.find(`[data-testid="${DossierTestId.overviewNewSource}"]`).trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('Dashboard')
  })
})

describe('Dossier — Lauf-Anreicherung (Redesign PR 4)', () => {
  it('Kennzahlstreifen zeigt Personas und Jobs, wenn bekannt', () => {
    const obj = makeObject({
      kind: 'lauf',
      personaCount: 12,
      jobs: [
        { runId: 'run_1', runType: 'simulation_run', status: 'completed', message: '', updatedAt: '2026-08-18T10:00:00Z', linkedIds: {} },
        { runId: 'run_0', runType: 'graph_build', status: 'completed', message: '', updatedAt: '2026-08-17T10:00:00Z', linkedIds: {} },
      ],
    })
    const wrapper = mountDossier(obj)

    const kpis = wrapper.find(`[data-testid="${DossierTestId.kpis}"]`).text()
    expect(kpis).toContain('12')
    expect(kpis).toContain('2')
  })

  it('Bestandteile Akteure/Ausgabe zeigen Zahl + Link, der Link navigiert', async () => {
    vi.mocked(getReport).mockResolvedValue({ success: true, data: { evidence_sections: 7 } } as never)
    const obj = makeObject({
      kind: 'lauf',
      personaCount: 8,
      jobs: [{ runId: 'run_1', runType: 'simulation_run', status: 'completed', message: '', updatedAt: '2026-08-18T10:00:00Z', linkedIds: { simulation_id: 'sim_1', report_id: 'rep_9' } }],
    })
    const wrapper = mountDossier(obj)
    await flushPromises()

    const parts = wrapper.findAll(`[data-testid="${DossierTestId.part}"]`)
    expect(parts).toHaveLength(2)
    expect(parts[0].text()).toContain('8')
    expect(parts[1].text()).toContain('7')

    await parts[1].find('button').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('StepReport')
    expect(router.currentRoute.value.params.reportId).toBe('rep_9')
  })

  it('Jobs-Zeitleiste zeigt alle Jobs des Laufs', () => {
    const obj = makeObject({
      kind: 'lauf',
      jobs: [
        { runId: 'run_new', runType: 'simulation_run', status: 'completed', message: '', updatedAt: '2026-08-18T10:00:00Z', linkedIds: {} },
        { runId: 'run_old', runType: 'graph_build', status: 'completed', message: '', updatedAt: '2026-08-17T10:00:00Z', linkedIds: {} },
      ],
    })
    const wrapper = mountDossier(obj)

    const timeline = wrapper.find(`[data-testid="${DossierTestId.jobsTimeline}"]`)
    expect(timeline.exists()).toBe(true)
    expect(timeline.findAll('li')).toHaveLength(2)
  })

  it('Jobs-Zeitleiste fehlt, wenn der Lauf keine Jobs traegt', () => {
    const obj = makeObject({ kind: 'lauf', jobs: [] })
    const wrapper = mountDossier(obj)

    expect(wrapper.find(`[data-testid="${DossierTestId.jobsTimeline}"]`).exists()).toBe(false)
  })
})

describe('Dossier — Bericht-Anreicherung (Redesign PR 4)', () => {
  it('zeigt Confidence-Verteilung und Red-Team-Befunde aus dem Report-Contract', async () => {
    vi.mocked(getReport).mockResolvedValue({
      success: true,
      data: {
        outline: { title: 'T', summary: 'S', sections: [{ title: 'Lage', description: 'D' }] },
        evidence_sections: 4,
        red_team_findings: ['Ein Befund'],
      },
    } as never)
    vi.mocked(getReportEvidence).mockResolvedValue({
      success: true,
      data: {
        sections: [
          {
            claims: [
              { confidence_label: 'high' },
              { confidence_label: 'low' },
              { confidence_label: 'low' },
            ],
            data_gaps: [],
          },
        ],
      },
    } as never)

    const obj = makeObject({ kind: 'bericht', id: 'rep_1' })
    const wrapper = mountDossier(obj)
    await flushPromises()

    const confidence = wrapper.find(`[data-testid="${DossierTestId.confidenceDistribution}"]`)
    expect(confidence.exists()).toBe(true)
    expect(confidence.text()).toContain('2')
    expect(confidence.text()).toContain('1')

    const redTeam = wrapper.find(`[data-testid="${DossierTestId.redTeamFindings}"]`)
    expect(redTeam.exists()).toBe(true)
    expect(redTeam.text()).toContain('Ein Befund')

    const kpis = wrapper.find(`[data-testid="${DossierTestId.kpis}"]`).text()
    expect(kpis).toContain('4')
  })

  it('Confidence-Verteilung und Red-Team-Befunde fehlen ohne Claims/Befunde', async () => {
    vi.mocked(getReport).mockResolvedValue({
      success: true,
      data: { outline: { title: 'T', summary: 'S', sections: [] }, evidence_sections: 0, red_team_findings: [] },
    } as never)
    vi.mocked(getReportEvidence).mockResolvedValue({ success: true, data: { sections: [] } } as never)

    const obj = makeObject({ kind: 'bericht', id: 'rep_2' })
    const wrapper = mountDossier(obj)
    await flushPromises()

    expect(wrapper.find(`[data-testid="${DossierTestId.confidenceDistribution}"]`).exists()).toBe(false)
    expect(wrapper.find(`[data-testid="${DossierTestId.redTeamFindings}"]`).exists()).toBe(false)
  })
})
