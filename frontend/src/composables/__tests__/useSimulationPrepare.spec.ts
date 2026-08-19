/**
 * Tests für useSimulationPrepare — Sub-Slice 34, Refs #203.
 *
 * Getestete Contracts:
 *   1. Erfolgsfall: startPrepare() ruft API mit korrektem Body, setzt
 *      isPreparing=true während des Calls, startet Polling und liefert true.
 *   2. Pending-Übergang: isPreparing ist deterministisch true zwischen
 *      startPrepare()-Aufruf und API-Antwort.
 *   3. Fehler-Pfad (4xx/5xx Envelope): API liefert success=false,
 *      Composable setzt error.value, ruft onStatusChange('error'), wirft nicht.
 *   4. Idempotenz/Re-Trigger: zweiter Aufruf bei laufendem ersten ist
 *      ein no-op (isPreparing guard), der erste Aufruf wird nicht unterbrochen.
 *   5. already_prepared: API signalisiert Simulation bereits vorbereitet,
 *      Composable hydratiert via probeAlreadyPrepared und setzt phase=3.
 *   6. Netzwerkfehler: Promise rejects, Composable setzt error.value,
 *      ruft onStatusChange('error'), gibt false zurück.
 *   7. probeAlreadyPrepared: keine Config vorhanden → kein State-Change.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock des api/simulation-Moduls BEVOR Import des Composables
vi.mock('../../api/simulation', () => ({
  prepareSimulation: vi.fn(),
  getPrepareStatus: vi.fn(),
  getSimulationProfilesRealtime: vi.fn(),
  getSimulationConfigRealtime: vi.fn(),
}))

import {
  prepareSimulation,
  getPrepareStatus,
  getSimulationProfilesRealtime,
  getSimulationConfigRealtime,
  type TaskStatusData,
  type ProfileRecord,
} from '../../api/simulation'
import type { ProfilesRealtimeResponse, ConfigRealtimeResponse } from '../../api/simulation'
import type { ApiEnvelope } from '../../api/envelope'
import { useSimulationPrepare } from '../useSimulationPrepare'

const mockPrepare = vi.mocked(prepareSimulation)
const mockGetStatus = vi.mocked(getPrepareStatus)
const mockGetProfiles = vi.mocked(getSimulationProfilesRealtime)
const mockGetConfig = vi.mocked(getSimulationConfigRealtime)

// -------------------------------------------------------------------------
// Helpers
// -------------------------------------------------------------------------

/** reason: service interceptor returns raw envelope body at runtime */
function makePrepareEnvelope(overrides: Record<string, unknown> = {}): unknown {
  return {
    success: true,
    data: {
      task_id: 'task-abc',
      expected_entities_count: 10,
      already_prepared: false,
      ...overrides,
    },
  }
}

function makeErrorEnvelope(error = 'Serverfehler'): unknown {
  return { success: false, error }
}

// Befund: `getSimulationProfilesRealtime` liefert laut api/simulation.ts
// `ApiEnvelope<ProfileRecord[]>` — `data` ist das Array direkt, kein
// `{profiles: [...]}`-Wrapper (den die alten Mocks hier vorgaukelten und den
// der Composable-Code ungeprüft annahm — siehe Bericht).
function makeProfilesEnvelope(profiles: ProfileRecord[] = []): ApiEnvelope<ProfilesRealtimeResponse> {
  // Der Endpunkt liefert ein Objekt MIT profiles-Feld
  // (backend/app/api/simulation_profiles.py:206).
  return { success: true, data: { simulation_id: 'sim_1', platform: 'reddit', count: profiles.length, profiles } }
}

function makeConfigEnvelope(config: Record<string, unknown> | null = null): ApiEnvelope<ConfigRealtimeResponse> {
  if (!config) return { success: false }
  // Die Konfiguration liegt im Feld `config` (simulation_profiles.py:598).
  return { success: true, data: { simulation_id: 'sim_1', config } }
}

function makeStatusEnvelope(status: string, progress = 100): unknown {
  return {
    success: true,
    data: { status, progress, message: '' },
  }
}

// -------------------------------------------------------------------------
// Test setup
// -------------------------------------------------------------------------

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()

  // Safe defaults so polling ticks don't crash
  mockGetStatus.mockResolvedValue(makeStatusEnvelope('running', 50) as ApiEnvelope<TaskStatusData>)
  mockGetProfiles.mockResolvedValue(makeProfilesEnvelope())
  mockGetConfig.mockResolvedValue(makeConfigEnvelope())
})

afterEach(() => {
  vi.useRealTimers()
})

// -------------------------------------------------------------------------
// Tests
// -------------------------------------------------------------------------

describe('useSimulationPrepare', () => {
  describe('Case 1 — Erfolgsfall: startPrepare ruft API korrekt auf und setzt State', () => {
    it('ruft prepareSimulation mit korrektem Body, gibt true zurück, setzt isPreparing=true', async () => {
      mockPrepare.mockResolvedValue(makePrepareEnvelope() as ApiEnvelope<TaskStatusData>)

      const composable = useSimulationPrepare()
      const onLog = vi.fn()
      const onStatusChange = vi.fn()

      const result = await composable.startPrepare({
        payload: { simulation_id: 'sim-001', use_llm_for_profiles: true, parallel_profile_count: 5 },
        onLog,
        onStatusChange,
      })

      expect(result).toBe(true)
      expect(mockPrepare).toHaveBeenCalledOnce()
      expect(mockPrepare).toHaveBeenCalledWith(
        expect.objectContaining({ simulation_id: 'sim-001' })
      )
      expect(onStatusChange).toHaveBeenCalledWith('processing')
      // Polling is running after successful start
      expect(composable.isPreparing.value).toBe(true)
      expect(composable.phase.value).toBe(1)
      expect(composable.expectedTotal.value).toBe(10)
    })

    // Issue #1034: Der Nenner zählt Personas, nicht Entitäten. Ohne
    // `persona_target` blieb er bei der Entitätenzahl stehen und der
    // Zähler lief darüber hinaus — „Erzeugt 22 / 7 Personas…".
    it('nimmt persona_target_count als Nenner, nicht expected_entities_count', async () => {
      mockPrepare.mockResolvedValue(makePrepareEnvelope({
        expected_entities_count: 7,
        persona_target: {
          entity_count: 7,
          persona_target_count: 50,
          floor_applied: true,
          floor: 50,
        },
      }) as ApiEnvelope<TaskStatusData>)

      const composable = useSimulationPrepare()

      await composable.startPrepare({
        payload: { simulation_id: 'sim-001', use_llm_for_profiles: true, parallel_profile_count: 5 },
        onLog: vi.fn(),
        onStatusChange: vi.fn(),
      })

      expect(composable.expectedTotal.value).toBe(50)
      expect(composable.personaFloorApplied.value).toBe(true)
    })

    it('meldet keinen gegriffenen Floor, wenn das Ziel der Entitätenzahl entspricht', async () => {
      mockPrepare.mockResolvedValue(makePrepareEnvelope({
        expected_entities_count: 80,
        persona_target: {
          entity_count: 80,
          persona_target_count: 80,
          floor_applied: false,
          floor: 50,
        },
      }) as ApiEnvelope<TaskStatusData>)

      const composable = useSimulationPrepare()

      await composable.startPrepare({
        payload: { simulation_id: 'sim-001', use_llm_for_profiles: true, parallel_profile_count: 5 },
        onLog: vi.fn(),
        onStatusChange: vi.fn(),
      })

      expect(composable.expectedTotal.value).toBe(80)
      expect(composable.personaFloorApplied.value).toBe(false)
    })

    it('fällt bei unbrauchbarem persona_target auf die Entitätenzahl zurück statt zu kippen', async () => {
      mockPrepare.mockResolvedValue(makePrepareEnvelope({
        expected_entities_count: 12,
        persona_target: { kaputt: true },
      }) as ApiEnvelope<TaskStatusData>)

      const composable = useSimulationPrepare()

      const result = await composable.startPrepare({
        payload: { simulation_id: 'sim-001', use_llm_for_profiles: true, parallel_profile_count: 5 },
        onLog: vi.fn(),
        onStatusChange: vi.fn(),
      })

      expect(result).toBe(true)
      expect(composable.expectedTotal.value).toBe(12)
      expect(composable.personaFloorApplied.value).toBe(false)
    })
  })

  describe('Case 2 — Pending-Übergang: isPreparing ist deterministisch true während des API-Calls', () => {
    it('isPreparing=true wird synchron gesetzt bevor das API-Promise resolves', async () => {
      let resolvePromise: (v: unknown) => void
      const deferred = new Promise<unknown>((res) => { resolvePromise = res })
      mockPrepare.mockReturnValue(deferred as Promise<ApiEnvelope<TaskStatusData>>)

      const composable = useSimulationPrepare()
      const callPromise = composable.startPrepare({
        payload: { simulation_id: 'sim-002' },
        onLog: vi.fn(),
        onStatusChange: vi.fn(),
      })

      // isPreparing is set synchronously on entry to startPrepare
      expect(composable.isPreparing.value).toBe(true)

      // Resolve and await
      resolvePromise!(makePrepareEnvelope())
      await callPromise

      // Still true because polling is active
      expect(composable.isPreparing.value).toBe(true)
    })
  })

  describe('Case 3 — Fehler-Pfad: API liefert success=false', () => {
    it('setzt error.value und ruft onStatusChange("error") ohne zu werfen', async () => {
      mockPrepare.mockResolvedValue(makeErrorEnvelope('Keine Entitäten gefunden.') as ApiEnvelope<TaskStatusData>)

      const composable = useSimulationPrepare()
      const onLog = vi.fn()
      const onStatusChange = vi.fn()

      // Must not throw
      const result = await composable.startPrepare({
        payload: { simulation_id: 'sim-003' },
        onLog,
        onStatusChange,
      })

      expect(result).toBe(false)
      expect(composable.error.value).toBe('Keine Entitäten gefunden.')
      expect(onStatusChange).toHaveBeenCalledWith('error')
      expect(composable.isPreparing.value).toBe(false)
    })

    it('Netzwerkfehler (rejected Promise): setzt error.value, gibt false zurück', async () => {
      mockPrepare.mockRejectedValue(new Error('Network Error'))

      const composable = useSimulationPrepare()
      const onStatusChange = vi.fn()

      const result = await composable.startPrepare({
        payload: { simulation_id: 'sim-004' },
        onLog: vi.fn(),
        onStatusChange,
      })

      expect(result).toBe(false)
      expect(composable.error.value).toBe('Network Error')
      expect(onStatusChange).toHaveBeenCalledWith('error')
      expect(composable.isPreparing.value).toBe(false)
    })
  })

  describe('Case 4 — Idempotenz/Re-Trigger: zweiter Aufruf bei laufendem ersten ist no-op', () => {
    it('zweiter startPrepare-Aufruf gibt false zurück und ruft API nur einmal', async () => {
      let resolveFirst: (v: unknown) => void
      const firstDeferred = new Promise<unknown>((res) => { resolveFirst = res })
      mockPrepare.mockReturnValueOnce(firstDeferred as Promise<ApiEnvelope<TaskStatusData>>)

      const composable = useSimulationPrepare()
      const opts = {
        payload: { simulation_id: 'sim-005' },
        onLog: vi.fn(),
        onStatusChange: vi.fn(),
      }

      // Start first call (still pending)
      const firstCall = composable.startPrepare(opts)
      expect(composable.isPreparing.value).toBe(true)

      // Second call while first is running
      const secondResult = await composable.startPrepare(opts)

      expect(secondResult).toBe(false)
      // API was only called once
      expect(mockPrepare).toHaveBeenCalledOnce()

      // Clean up first call
      resolveFirst!(makePrepareEnvelope())
      await firstCall
    })
  })

  describe('Case 5 — already_prepared: probeAlreadyPrepared hydratiert State korrekt', () => {
    it('setzt phase=3 und simulationConfig wenn Config vorhanden', async () => {
      const fakeConfig = { time_config: { total_simulation_hours: 24, minutes_per_round: 60 } }
      mockGetConfig.mockResolvedValue(makeConfigEnvelope(fakeConfig))
      mockGetProfiles.mockResolvedValue(makeProfilesEnvelope([{ username: 'u1' } as ProfileRecord]))

      const composable = useSimulationPrepare()
      const onLog = vi.fn()
      const onStatusChange = vi.fn()

      await composable.probeAlreadyPrepared('sim-006', { onLog, onStatusChange })

      expect(composable.phase.value).toBe(3)
      expect(composable.simulationConfig.value).toEqual(fakeConfig)
      expect(onStatusChange).toHaveBeenCalledWith('completed')
    })

    it('kein State-Change wenn Config-Endpunkt kein Config zurückgibt', async () => {
      mockGetConfig.mockResolvedValue(makeConfigEnvelope(null))

      const composable = useSimulationPrepare()
      await composable.probeAlreadyPrepared('sim-007', { onLog: vi.fn(), onStatusChange: vi.fn() })

      expect(composable.phase.value).toBe(0)
      expect(composable.simulationConfig.value).toBeNull()
    })
  })

  describe('Case 6 — fehlende simulationId: startPrepare bricht früh ab', () => {
    it('ruft onStatusChange("error") ohne API-Call, gibt false zurück', async () => {
      const composable = useSimulationPrepare()
      const onStatusChange = vi.fn()

      const result = await composable.startPrepare({
        payload: { simulation_id: '' },
        onLog: vi.fn(),
        onStatusChange,
      })

      expect(result).toBe(false)
      expect(mockPrepare).not.toHaveBeenCalled()
      expect(onStatusChange).toHaveBeenCalledWith('error')
    })
  })

  describe('Case 8 — fetchProfilesRealtime: im Return-Objekt als öffentliche Methode exponiert (Regression Sub-Slice 36, Closes #292)', () => {
    it('exposes fetchProfilesRealtime als Funktion', () => {
      const composable = useSimulationPrepare()
      // MUST remain a function — removing this export causes ReferenceError in Step2EnvSetup.vue
      expect(typeof composable.fetchProfilesRealtime).toBe('function')
    })

    it('fetchProfilesRealtime() aktualisiert profiles.value wenn API Erfolg liefert', async () => {
      const fakeProfiles = [{ username: 'tester' } as ProfileRecord]
      mockGetProfiles.mockResolvedValue(makeProfilesEnvelope(fakeProfiles))

      const composable = useSimulationPrepare()
      // Set a simulationId so the guard passes
      await composable.probeAlreadyPrepared('sim-100', { onLog: vi.fn(), onStatusChange: vi.fn() })

      await composable.fetchProfilesRealtime()

      expect(mockGetProfiles).toHaveBeenCalled()
      expect(composable.profiles.value).toEqual(fakeProfiles)
    })
  })

  describe('Case 7 — reset: setzt alle State-Werte zurück auf Initialwerte', () => {
    it('reset() nach erfolgreichem Start liefert initialen State', async () => {
      mockPrepare.mockResolvedValue(makePrepareEnvelope() as ApiEnvelope<TaskStatusData>)

      const composable = useSimulationPrepare()
      await composable.startPrepare({
        payload: { simulation_id: 'sim-008' },
        onLog: vi.fn(),
        onStatusChange: vi.fn(),
      })

      expect(composable.isPreparing.value).toBe(true)

      composable.reset()

      expect(composable.phase.value).toBe(0)
      expect(composable.isPreparing.value).toBe(false)
      expect(composable.prepareProgress.value).toBe(0)
      expect(composable.profiles.value).toHaveLength(0)
      expect(composable.expectedTotal.value).toBeNull()
      expect(composable.simulationConfig.value).toBeNull()
      expect(composable.error.value).toBeNull()
    })
  })
})
