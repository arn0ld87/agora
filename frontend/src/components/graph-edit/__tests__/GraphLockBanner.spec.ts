import { describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'
import { mount } from '@vue/test-utils'
import GraphLockBanner from '../GraphLockBanner.vue'
import { GraphEditTestId } from '@/contracts/testIds'
import type { GraphLockStatus } from '@/composables/graph-library/useGraphLock'
import type { GraphDuplicate } from '@/composables/graph-library/useGraphDuplicate'
import type { GraphDuplicateRun, GraphLockUser } from '@/contracts/graphEditContract'
import { makeI18n, makeRouter } from './fixtures'

const sim = (id: string) => ({ simulation_id: id, status: 'completed', project_id: 'p1', branch_name: null })

interface BannerProps {
  status: GraphLockStatus
  usedBy: GraphLockUser[]
  loading: boolean
  error: string | null
  duplicate?: GraphDuplicate
  duplicateName?: string
}

/**
 * Attrappe des Kopierauftrags mit echten Refs, damit der Test den Zustand wie
 * die Laufzeit veraendern kann, ohne den Composable nachzufahren.
 */
function fakeDuplicate(
  over: {
    status?: GraphDuplicateRun['status'] | null
    percent?: number
    message?: string
    projectId?: string | null
    busy?: boolean
    error?: { kind: string; message: string } | null
  } = {},
): GraphDuplicate {
  const status = ref<GraphDuplicateRun['status'] | null>(over.status === undefined ? null : over.status)
  const projectId = over.projectId === undefined ? 'proj_kopie' : over.projectId
  const completed = computed(() => status.value === 'completed')
  const failed = computed(() => status.value === 'failed' || status.value === 'stopped')
  return {
    job: ref(projectId ? { graphId: 'g1', projectId, runId: 'run_dup_1' } : null),
    status,
    progress: ref({ percent: over.percent ?? 0, message: over.message ?? '' }),
    error: ref(over.error ?? null),
    busy: ref(over.busy ?? false),
    running: computed(() => status.value !== null && !completed.value && !failed.value),
    completed,
    failed,
    copyProjectId: computed(() => (completed.value ? projectId : null)),
    start: vi.fn(),
    clearError: vi.fn(),
    dispose: vi.fn(),
  } as unknown as GraphDuplicate
}

async function mountBanner(over: Partial<BannerProps> = {}) {
  const router = makeRouter()
  await router.push('/graphs/p1')
  await router.isReady()
  const wrapper = mount(GraphLockBanner, {
    props: { status: 'editable', usedBy: [], loading: false, error: null, ...over },
    global: { plugins: [makeI18n(), router] },
  })
  await wrapper.vm.$nextTick()
  return wrapper
}

describe('GraphLockBanner', () => {
  it('nennt bei „gesperrt“ den Grund und die Läufe, die ihn verwenden', async () => {
    const wrapper = await mountBanner({ status: 'locked', usedBy: [sim('sim_44fee3d638cf')] })
    expect(wrapper.get(`[data-testid="${GraphEditTestId.lockBanner}"]`).attributes('role')).toBe('status')
    expect(wrapper.text()).toContain('Eine Simulation verwendet diesen Graphen')
    expect(wrapper.text()).toContain('Kopie')
    expect(wrapper.get(`[data-testid="${GraphEditTestId.lockUsedBy}"]`).text()).toContain('sim_44fee3d638cf')
    // Der Ausweg ist benannt (Text, nicht nur ein deaktivierter Knopf).
    expect(wrapper.text()).toContain('Kopie')
  })

  it('zeigt bei „bearbeitbar“ keinen Sperrtext', async () => {
    const wrapper = await mountBanner({ status: 'editable' })
    expect(wrapper.get(`[data-testid="${GraphEditTestId.lockBadge}"]`).text()).toBe('Bearbeitbar')
    expect(wrapper.text()).not.toContain('Eine Simulation verwendet')
    expect(wrapper.text()).not.toContain('Kopie')
  })

  it('behandelt „unbekannt“ als gesperrt und nennt das Prüfen, nicht den Zustand', async () => {
    const wrapper = await mountBanner({ status: 'unknown' })
    expect(wrapper.get(`[data-testid="${GraphEditTestId.lockBadge}"]`).text()).toBe('Sperrzustand wird geprüft')
    expect(wrapper.text()).not.toContain('Eine Simulation verwendet')
  })

  it('meldet eine gescheiterte Prüfung sichtbar und bietet das Neuladen an', async () => {
    const wrapper = await mountBanner({ status: 'error', error: 'offline' })
    expect(wrapper.get(`[data-testid="${GraphEditTestId.lockBanner}"]`).attributes('role')).toBe('alert')
    expect(wrapper.text()).toContain('konnte nicht ermittelt werden')
    expect(wrapper.text()).toContain('offline')

    await wrapper.get('[data-testid="graph-edit-lock-reload"]').trigger('click')
    expect(wrapper.emitted('reload')).toHaveLength(1)
  })

  it('meldet das Neuladen des Sperrzustands, solange geprüft wird', async () => {
    const wrapper = await mountBanner({ status: 'unknown', loading: true })
    expect(wrapper.get(`[data-testid="${GraphEditTestId.lockBadge}"]`).attributes('aria-busy')).toBe('true')
  })
})

describe('GraphLockBanner — Ausweg über eine Kopie', () => {
  it('bietet den Ausweg als Knopf an, nicht nur als Wort', async () => {
    const wrapper = await mountBanner({ status: 'locked', usedBy: [sim('sim_1')], duplicate: fakeDuplicate() })
    const button = wrapper.get(`[data-testid="${GraphEditTestId.duplicateStart}"]`)
    expect(button.text()).toBe('Kopie anlegen')
    // Der Name steht in einem Feld mit Label, nicht als Platzhalter im Knopf.
    const name = wrapper.get(`[data-testid="${GraphEditTestId.duplicateName}"]`)
    expect(name.attributes('type')).toBe('text')
    expect(wrapper.find(`label [data-testid="${GraphEditTestId.duplicateName}"]`).exists()).toBe(true)
  })

  it('sendet den getippten Namen mit und behält einen leeren Namen fuer sich', async () => {
    const wrapper = await mountBanner({
      status: 'locked',
      duplicate: fakeDuplicate(),
      duplicateName: 'Kreistag (Kopie)',
    })
    await wrapper.get(`[data-testid="${GraphEditTestId.duplicateName}"]`).setValue('')
    await wrapper.get(`[data-testid="${GraphEditTestId.duplicateStart}"]`).trigger('click')
    // Der Vertrag verlangt einen Namen; ohne ihn wird nichts gemeldet.
    expect(wrapper.emitted('duplicate')).toBeUndefined()

    await wrapper.get(`[data-testid="${GraphEditTestId.duplicateName}"]`).setValue('  Moorhagen Kopie  ')
    await wrapper.get(`[data-testid="${GraphEditTestId.duplicateStart}"]`).trigger('click')
    expect(wrapper.emitted('duplicate')).toEqual([['Moorhagen Kopie']])
  })

  it('nennt waehrend des Auftrags den Zustand, nicht eine Kopie', async () => {
    const dup = fakeDuplicate({ status: 'processing', percent: 45, message: 'Quelle wird gelesen' })
    const wrapper = await mountBanner({ status: 'locked', duplicate: dup })
    const state = wrapper.get(`[data-testid="${GraphEditTestId.duplicateState}"]`)
    expect(state.attributes('data-status')).toBe('processing')
    expect(state.text()).toContain('Kopie wird angelegt')
    expect(state.text()).toContain('45')
    // Ohne Endzustand gibt es kein Ziel und keine Behauptung.
    expect(state.find(`[data-testid="${GraphEditTestId.duplicateOpen}"]`).exists()).toBe(false)
  })

  it('verlinkt die Kopie erst bei „completed“', async () => {
    const dup = fakeDuplicate({ status: 'completed', percent: 100 })
    const wrapper = await mountBanner({ status: 'locked', duplicate: dup })
    const link = wrapper.get(`[data-testid="${GraphEditTestId.duplicateOpen}"]`)
    expect(link.attributes('href')).toBe('/graphs/proj_kopie')
    expect(link.text()).toContain('Kopie ist fertig')
  })

  it('nennt einen fehlgeschlagenen Auftrag als solchen', async () => {
    const dup = fakeDuplicate({ status: 'failed', percent: 30, message: 'Zielprojekt liess sich nicht anlegen' })
    const wrapper = await mountBanner({ status: 'locked', duplicate: dup })
    expect(wrapper.get(`[data-testid="${GraphEditTestId.duplicateState}"]`).text()).toContain(
      'Die Kopie wurde nicht angelegt',
    )
    expect(wrapper.find(`[data-testid="${GraphEditTestId.duplicateOpen}"]`).exists()).toBe(false)
    expect(wrapper.get(`[data-testid="${GraphEditTestId.duplicateStart}"]`).attributes('disabled')).toBeDefined()
  })

  it('zeigt 409 und 503 des Kopierpfads unterscheidbar', async () => {
    const build = await mountBanner({
      status: 'locked',
      duplicate: fakeDuplicate({ error: { kind: 'build_running', message: 'wird gebaut' } }),
    })
    expect(build.get(`[data-testid="${GraphEditTestId.duplicateError}"]`).text()).toContain('gerade gebaut')

    const down = await mountBanner({
      status: 'locked',
      duplicate: fakeDuplicate({ error: { kind: 'unavailable', message: 'Dienst aus' } }),
    })
    const text = down.get(`[data-testid="${GraphEditTestId.duplicateError}"]`).text()
    expect(text).toContain('Kopierpfad ist gerade nicht verfügbar')
    expect(text).toContain('Dienst aus')
  })

  it('ohne gesperrten Graphen gibt es keinen Kopier-Knopf', async () => {
    const editable = await mountBanner({ duplicate: fakeDuplicate() })
    expect(editable.find(`[data-testid="${GraphEditTestId.duplicateStart}"]`).exists()).toBe(false)

    const unknown = await mountBanner({ status: 'unknown', duplicate: fakeDuplicate() })
    expect(unknown.find(`[data-testid="${GraphEditTestId.duplicateStart}"]`).exists()).toBe(false)
  })

  it('ohne verdrahteten Auftrag bleibt der Ausweg Text', async () => {
    const wrapper = await mountBanner({ status: 'locked', usedBy: [sim('sim_1')] })
    expect(wrapper.text()).toContain('Kopie')
    expect(wrapper.find(`[data-testid="${GraphEditTestId.duplicateStart}"]`).exists()).toBe(false)
  })

  it('waehrend des Sendens ist der Knopf gesperrt', async () => {
    const dup = fakeDuplicate({ busy: true })
    const wrapper = await mountBanner({ status: 'locked', duplicate: dup })
    expect(wrapper.get(`[data-testid="${GraphEditTestId.duplicateStart}"]`).attributes('disabled')).toBeDefined()
  })
})
