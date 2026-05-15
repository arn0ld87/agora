/**
 * commandsStore — Unit-Tests
 *
 * 7 Tests:
 * 1. buildStaticCommands liefert alle Top-Level-Nav-Routes als Commands
 * 2. filter() filtert korrekt nach Query
 * 3. getOrdered(): Recent-Commands erscheinen zuerst
 * 4. getOrdered() ohne Recent liefert unveraenderte Reihenfolge
 * 5. (Phase C) dynamicCommands erscheinen wenn runs-Store mit laufendem Run gefuettert wird
 * 6. (Phase C) filter() matchet dynamische Sim-Commands per Keyword "sim"
 * 7. (Phase C) unbindDynamicCommands() leert dynamicCommands + erlaubt Re-Bind
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { ref, nextTick } from 'vue'

// localStorage-Mock
const lsMock = (() => {
  const s: Record<string, string> = {}
  return {
    getItem: (k: string) => s[k] ?? null,
    setItem: (k: string, v: string) => { s[k] = v },
    removeItem: (k: string) => { delete s[k] },
    clear: () => { Object.keys(s).forEach((k) => { delete s[k] }) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: lsMock, writable: true })

// useRunsPolling-Mock — gibt kontrollierten runs-Ref zurueck
const mockRuns = ref<unknown[]>([])
vi.mock('@/composables/useRunsPolling', () => ({
  useRunsPolling: () => ({
    runs: mockRuns,
    loading: ref(false),
    error: ref(''),
    isRunning: ref(false),
    start: vi.fn().mockResolvedValue(undefined),
    stop: vi.fn(),
    refresh: vi.fn(),
  }),
}))

import { useCommandsStore } from '../commandsStore'
import { useCommandPalette } from '@/composables/useCommandPalette'

// Router-Mock: router.push ist ein vi.fn()
const routerMock = {
  push: vi.fn().mockResolvedValue(undefined),
}

describe('commandsStore', () => {
  beforeEach(() => {
    lsMock.clear()
    mockRuns.value = []
    setActivePinia(createPinia())
    const { clearRecent } = useCommandPalette()
    clearRecent()
    routerMock.push.mockClear()
  })

  it('buildStaticCommands liefert alle Nav-Top-Level-Routes', () => {
    const store = useCommandsStore()
    const cmds = store.buildStaticCommands(routerMock as never)
    // Mindestens: Dashboard, Runs, History + Settings-Unterseiten
    const ids = cmds.map((c) => c.id)
    expect(ids).toContain('nav:dashboard')
    expect(ids).toContain('nav:runs')
    expect(ids).toContain('nav:history')
    expect(ids).toContain('nav:settings-general')
    expect(ids).toContain('nav:settings-llm-routing')
    expect(cmds.length).toBeGreaterThanOrEqual(5)
  })

  it('filter() gibt alle Commands zurueck wenn query leer', () => {
    const store = useCommandsStore()
    const cmds = store.buildStaticCommands(routerMock as never)
    const result = store.filter(cmds, '')
    expect(result.length).toBe(cmds.length)
  })

  it('filter() filtert korrekt nach Query-String', () => {
    const store = useCommandsStore()
    const cmds = store.buildStaticCommands(routerMock as never)
    const result = store.filter(cmds, 'dashboard')
    expect(result.length).toBeGreaterThanOrEqual(1)
    expect(result.every((c) => c.label.toLowerCase().includes('dashboard') || c.id.includes('dashboard'))).toBe(true)

    const noResult = store.filter(cmds, 'xyznotexistent123')
    expect(noResult.length).toBe(0)
  })

  it('getOrdered() schiebt Recent-Commands an den Anfang', () => {
    const store = useCommandsStore()
    const { pushRecent } = useCommandPalette()
    const cmds = store.buildStaticCommands(routerMock as never)

    // 'nav:runs' als Recent setzen
    pushRecent('nav:runs')
    const ordered = store.getOrdered(cmds)

    expect(ordered[0].id).toBe('nav:runs')
    // group ist 'recent' fuer priorisierte Commands
    expect(ordered[0].group).toBe('recent')
    // Restliche Commands folgen
    expect(ordered.length).toBe(cmds.length)
  })

  it('getOrdered() ohne Recent liefert unveraenderte Reihenfolge', () => {
    const store = useCommandsStore()
    const cmds = store.buildStaticCommands(routerMock as never)
    const ordered = store.getOrdered(cmds)
    expect(ordered.map((c) => c.id)).toEqual(cmds.map((c) => c.id))
  })

  // -------------------------------------------------------------------------
  // Phase C — dynamische Commands
  // -------------------------------------------------------------------------

  it('(Phase C) dynamicCommands erscheinen wenn laufender Run vorhanden', async () => {
    const store = useCommandsStore()
    store.bindDynamicCommands(routerMock as never)

    // Run mit Status 'processing' einfuegen
    mockRuns.value = [
      {
        run_id: 'run-abc-123',
        run_type: 'simulation',
        entity_id: 'sim-entity-456',
        status: 'processing',
        progress: 42,
        message: '',
        started_at: '2026-05-15T10:00:00Z',
        updated_at: '2026-05-15T10:01:00Z',
        metadata: {},
        linked_ids: {},
        artifacts: {},
        resume_capability: {},
        summary: { document_name: 'Test-Kampagne', model: null, persona_count: 10, graph_id: null, graph_name: null, branch_name: null },
      },
    ]

    // Watch-Reaktivitaet abwarten (Vue flushed Watchers asynchron)
    await nextTick()

    const dynCmds = store.dynamicCommands
    expect(dynCmds.length).toBeGreaterThanOrEqual(1)
    const simCmd = dynCmds.find((c) => c.id === 'sim:run-abc-123')
    expect(simCmd).toBeDefined()
    expect(simCmd?.group).toBe('sim')
    expect(simCmd?.label).toContain('Test-Kampagne')
    expect(simCmd?.keywords).toContain('simulation')
  })

  it('(Phase C) filter() matchet dynamische Sim-Commands per Keyword "sim"', async () => {
    const store = useCommandsStore()
    store.bindDynamicCommands(routerMock as never)

    mockRuns.value = [
      {
        run_id: 'run-xyz-789',
        run_type: 'simulation',
        entity_id: 'sim-ent-789',
        status: 'pending',
        progress: 0,
        message: '',
        started_at: '2026-05-15T11:00:00Z',
        updated_at: '2026-05-15T11:00:00Z',
        metadata: {},
        linked_ids: {},
        artifacts: {},
        resume_capability: {},
        summary: null,
      },
    ]

    await nextTick()

    const dynCmds = store.dynamicCommands
    const filtered = store.filter(dynCmds, 'sim')
    expect(filtered.length).toBeGreaterThanOrEqual(1)
    expect(filtered.some((c) => c.id.startsWith('sim:'))).toBe(true)
  })

  it('(Phase C) unbindDynamicCommands() leert Commands und erlaubt Re-Bind', async () => {
    const store = useCommandsStore()
    store.bindDynamicCommands(routerMock as never)

    mockRuns.value = [
      {
        run_id: 'run-del-001',
        run_type: 'simulation',
        entity_id: 'sim-del-001',
        status: 'processing',
        progress: 10,
        message: '',
        started_at: '2026-05-15T12:00:00Z',
        updated_at: '2026-05-15T12:00:00Z',
        metadata: {},
        linked_ids: {},
        artifacts: {},
        resume_capability: {},
        summary: null,
      },
    ]

    await nextTick()
    expect(store.dynamicCommands.length).toBeGreaterThanOrEqual(1)

    // Unbind leert
    store.unbindDynamicCommands()
    expect(store.dynamicCommands.length).toBe(0)

    // Re-Bind funktioniert (kein Fehler, neuer Watch).
    // Nach Re-Bind reagiert der neue Watch bei naechster Aenderung.
    // Wir aendern mockRuns minimal, um den Watch zu triggern.
    store.bindDynamicCommands(routerMock as never)
    mockRuns.value = [...mockRuns.value] // neue Array-Referenz triggert watch
    await nextTick()
    expect(store.dynamicCommands.length).toBeGreaterThanOrEqual(1)
  })
})
