import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'

const h_ = await vi.hoisted(async () => {
  const { ref, computed } = await import('vue')
  const kind = ref<string>('notStarted')
  const state = {
    stateKind: computed(() => kind.value),
    currentRound: ref<number | null>(null),
    totalRounds: ref<number | null>(null),
    totalActions: ref<number | null>(null),
    twitterActions: ref<number | null>(null),
    redditActions: ref<number | null>(null),
    costMicros: ref<number | null>(null),
    terminationReason: ref<string | null>(null),
    runError: ref<string | null>(null),
    error: ref<string | null>(null),
    reload: vi.fn(),
    adoptRunId: vi.fn(),
  }
  const control = {
    busy: ref<string | null>(null),
    error: ref<string | null>(null),
    start: vi.fn(),
    stop: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(),
    plannedModel: vi.fn(),
  }
  return { kind, state, control }
})

vi.mock('@/composables/run/simulation/useSimulationRunState', () => ({ useSimulationRunState: () => h_.state }))
vi.mock('@/composables/run/simulation/useSimulationControl', () => ({ useSimulationControl: () => h_.control }))

import RunSimHeader from '../RunSimHeader.vue'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'de', messages: { de } })
let wrapper: VueWrapper | null = null

function mountHeader(props: Record<string, unknown> = {}) {
  wrapper = mount(RunSimHeader, {
    props: { simulationId: 'sim_1', ...props },
    global: { plugins: [i18n] },
    attachTo: document.body,
  })
  return wrapper
}
const byId = (id: string) => document.body.querySelector(`[data-testid="${id}"]`) as HTMLElement | null

beforeEach(() => {
  h_.kind.value = 'notStarted'
  h_.state.currentRound.value = null
  h_.state.totalRounds.value = null
  h_.state.totalActions.value = null
  h_.state.twitterActions.value = null
  h_.state.redditActions.value = null
  h_.state.costMicros.value = null
  h_.state.terminationReason.value = null
  h_.state.runError.value = null
  h_.state.error.value = null
  h_.control.busy.value = null
  h_.control.error.value = null
  h_.control.plannedModel.mockReturnValue('std-model')
  h_.control.start.mockReset()
  h_.control.stop.mockReset()
  h_.control.pause.mockReset()
  h_.control.resume.mockReset()
  h_.state.reload.mockReset()
  h_.state.adoptRunId.mockReset()
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  document.body.innerHTML = ''
})

describe('RunSimHeader', () => {
  it('zeigt vor dem Start den Zustand, das geplante Modell als Text und nur den Startknopf', () => {
    mountHeader()
    expect(byId('run-state-mark')?.textContent).toContain('Nicht gestartet')
    expect(byId('sim-header-model')?.textContent).toContain('std-model')
    expect(byId('sim-header-round')?.textContent).toContain('Noch keine Runde')
    expect(byId('sim-header-cost')?.textContent).toContain('nicht erfasst')
    expect(byId('sim-header-start')).not.toBeNull()
    expect(byId('sim-header-stop')).toBeNull()
    expect(byId('sim-header-pause')).toBeNull()
    // Modell ist reiner Text, kein Auswahl-Bedienelement.
    expect(wrapper!.find('select, [role="combobox"], [role="listbox"]').exists()).toBe(false)
  })

  it('zeigt im Lauf Runde x von y, Beiträge, Kosten und die gelaufene Route', () => {
    h_.kind.value = 'running'
    h_.state.currentRound.value = 4
    h_.state.totalRounds.value = 24
    h_.state.totalActions.value = 42
    h_.state.twitterActions.value = 30
    h_.state.redditActions.value = 12
    h_.state.costMicros.value = 1_500_000
    mountHeader({ route: { model: 'run-model', providerId: 'prov' } })
    expect(byId('sim-header-round')?.textContent).toBe('Runde 4 von 24')
    expect(byId('sim-header-posts')?.textContent).toBe('42 (30 Twitter · 12 Reddit)')
    expect(byId('sim-header-cost')?.textContent).toMatch(/1,50/)
    expect(byId('sim-header-model')?.textContent).toBe('run-model')
    expect(byId('sim-header-pause')).not.toBeNull()
    expect(byId('sim-header-stop')).not.toBeNull()
    expect(byId('sim-header-start')).toBeNull()
  })

  it('zeigt bei Pause Fortsetzen statt Pausieren', () => {
    h_.kind.value = 'paused'
    mountHeader()
    expect(byId('sim-header-resume')).not.toBeNull()
    expect(byId('sim-header-pause')).toBeNull()
  })

  it('sperrt Starten ohne fertige Personas und nennt den Grund', () => {
    mountHeader({ personasReady: false })
    const btn = byId('sim-header-start') as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    expect(btn.getAttribute('aria-describedby')).toBe('sim-head-blocked')
    expect(byId('sim-header-blocked')?.textContent).toContain('Personas')
  })

  it('startet, übernimmt die run_id und meldet started', async () => {
    h_.control.start.mockResolvedValue({ runId: 'run_9' })
    const w = mountHeader()
    await (byId('sim-header-start') as HTMLButtonElement).click()
    await flushPromises()
    expect(h_.control.start).toHaveBeenCalledTimes(1)
    expect(h_.state.adoptRunId).toHaveBeenCalledWith('run_9')
    expect(w.emitted('started')).toEqual([['run_9']])
  })

  it('zeigt einen Startfehler als role=alert und meldet nicht started', async () => {
    h_.control.start.mockImplementation(async () => {
      h_.control.error.value = 'Kostenbudget erschöpft'
      return null
    })
    const w = mountHeader()
    ;(byId('sim-header-start') as HTMLButtonElement).click()
    await flushPromises()
    const alert = byId('sim-header-error')
    expect(alert?.getAttribute('role')).toBe('alert')
    expect(alert?.textContent).toContain('Kostenbudget erschöpft')
    expect(w.emitted('started')).toBeUndefined()
  })

  it('stoppt erst nach Bestätigung im Dialog', async () => {
    h_.kind.value = 'running'
    h_.control.stop.mockResolvedValue(true)
    const w = mountHeader()
    ;(byId('sim-header-stop') as HTMLButtonElement).click()
    await flushPromises()
    expect(h_.control.stop).not.toHaveBeenCalled()
    expect(byId('sim-header-stop-dialog')).not.toBeNull()

    ;(byId('sim-header-stop-confirm') as HTMLButtonElement).click()
    await flushPromises()
    expect(h_.control.stop).toHaveBeenCalledTimes(1)
    expect(h_.state.reload).toHaveBeenCalled()
    expect(w.emitted('changed')).toHaveLength(1)
  })

  it('bricht den Stoppdialog ab, ohne zu stoppen', async () => {
    h_.kind.value = 'running'
    mountHeader()
    ;(byId('sim-header-stop') as HTMLButtonElement).click()
    await flushPromises()
    ;(byId('sim-header-stop-cancel') as HTMLButtonElement).click()
    await flushPromises()
    expect(h_.control.stop).not.toHaveBeenCalled()
  })

  it('nennt bei Stopp, Budgetabbruch und Neustart-Fehler den Grund', () => {
    h_.kind.value = 'budget'
    h_.state.terminationReason.value = 'budget_cost'
    mountHeader()
    expect(byId('run-state-mark')?.textContent).toContain('Budget erschöpft')
    expect(byId('sim-header-reason')?.textContent).toContain('Kostenbudget erschöpft')
    wrapper!.unmount()

    h_.kind.value = 'failed'
    h_.state.terminationReason.value = 'process_restart'
    mountHeader()
    expect(byId('sim-header-reason')?.textContent).toContain('Prozess wurde neu gestartet')
    wrapper!.unmount()

    h_.kind.value = 'stopped'
    h_.state.terminationReason.value = null
    mountHeader()
    expect(byId('sim-header-reason')?.textContent).toContain('Gestoppt')
    expect(byId('sim-header-reason')?.textContent).toContain('Grund nicht erfasst')
  })

  it('trägt Zustandswechsel in einer aria-live-Region', async () => {
    mountHeader()
    const live = byId('sim-header-live')!
    expect(live.getAttribute('aria-live')).toBe('polite')
    expect(live.textContent).toContain('Nicht gestartet')
    h_.kind.value = 'running'
    await flushPromises()
    expect(live.textContent).toContain('Läuft')
  })
})
