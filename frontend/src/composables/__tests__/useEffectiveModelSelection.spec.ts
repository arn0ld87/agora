/**
 * useEffectiveModelSelection — Spec-Tests für den Phase-1-Root-Cause-Fix
 * "inkonsistente Modellauswahl" (frontend-next, PHASE-1-DIVERGENZ.md).
 *
 * Coverage:
 *  1. effectiveRoute spiegelt routing/defaults.global_default direkt
 *  2. effectiveRef leitet AiModelRef via Adapter aus global_default ab
 *  3. effectiveRef ist null ohne provider_id/model in global_default
 *  4. setGlobalSelection ruft setGlobalDefault (routing) mit der korrekt
 *     gemappten LlmRoute (provider_connection_id → provider_id, model_id → model)
 *  5. setGlobalSelection ruft setActiveLlmConfig (active-config) mit denselben
 *     Werten im Gleichschritt
 *  6. setGlobalSelection: Kanon (routing) wird VOR active-config geschrieben
 *  7. ensureLoaded lädt routing-defaults + connections, wenn noch nicht geladen
 *  8. ensureLoaded überspringt defaultsStore.load() idempotent bei hasLoadedOnce,
 *     lädt connections aber weiterhin
 *  9. ensureLoaded propagiert Fehler aus defaultsStore.load() nach error
 * 10. ensureLoaded propagiert Fehler aus providersStore.loadConnections() nach error
 * 11. setGlobalSelection propagiert Fehler aus setGlobalDefault, ruft
 *     setActiveLlmConfig dann NICHT auf
 * 12. setGlobalSelection propagiert Fehler aus setActiveLlmConfig
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { LlmRoute } from '@/contracts/llmRoute'
import type { AiModelRef } from '@/contracts/aiModelRef'

const providersStore = vi.hoisted(() => ({
  connections: {} as Record<string, any>,
  loadConnections: vi.fn(),
}))

const defaultsStore = vi.hoisted(() => ({
  globalDefault: {
    stage: null,
    provider_id: null,
    model: null,
    temperature: null,
    max_tokens: null,
    reasoning_effort: 'none',
    provider_options: {},
  } as LlmRoute,
  hasLoadedOnce: false,
  load: vi.fn(),
  setGlobalDefault: vi.fn(),
}))

vi.mock('@/store/aiModels', () => ({
  useLlmProvidersStore: () => providersStore,
  useLlmRoutingDefaultsStore: () => defaultsStore,
}))

const setActiveLlmConfigMock = vi.hoisted(() => vi.fn())
vi.mock('@/api/llmRouting', () => ({
  setActiveLlmConfig: setActiveLlmConfigMock,
}))

import { useEffectiveModelSelection } from '../useEffectiveModelSelection'

function makeRoute(overrides: Partial<LlmRoute> = {}): LlmRoute {
  return {
    stage: null,
    provider_id: 'conn-1',
    model: 'qwen3',
    temperature: null,
    max_tokens: null,
    reasoning_effort: 'none',
    provider_options: {},
    ...overrides,
  }
}

function makeRef(overrides: Partial<AiModelRef> = {}): AiModelRef {
  return {
    provider_connection_id: 'conn-xyz',
    model_id: 'gpt-4o',
    source: 'explicit',
    ...overrides,
  }
}

describe('useEffectiveModelSelection (Phase-1 Kanon-Fix)', () => {
  beforeEach(() => {
    providersStore.connections = {}
    providersStore.loadConnections.mockReset().mockResolvedValue(undefined)

    defaultsStore.globalDefault = makeRoute()
    defaultsStore.hasLoadedOnce = false
    defaultsStore.load.mockReset().mockResolvedValue(undefined)
    defaultsStore.setGlobalDefault.mockReset().mockResolvedValue(undefined)

    setActiveLlmConfigMock.mockReset().mockResolvedValue({})
  })

  it('effectiveRoute spiegelt global_default direkt', () => {
    defaultsStore.globalDefault = makeRoute({ provider_id: 'conn-42', model: 'llama3' })
    const { effectiveRoute } = useEffectiveModelSelection()
    expect(effectiveRoute.value).toEqual(defaultsStore.globalDefault)
  })

  it('effectiveRef leitet AiModelRef aus global_default ab (Adapter)', () => {
    defaultsStore.globalDefault = makeRoute({ provider_id: 'conn-42', model: 'llama3' })
    const { effectiveRef } = useEffectiveModelSelection()
    expect(effectiveRef.value).toMatchObject({
      provider_connection_id: 'conn-42',
      model_id: 'llama3',
    })
  })

  it('effectiveRef ist null, wenn global_default kein Provider/Modell trägt', () => {
    defaultsStore.globalDefault = makeRoute({ provider_id: null, model: null })
    const { effectiveRef } = useEffectiveModelSelection()
    expect(effectiveRef.value).toBeNull()
  })

  it('setGlobalSelection schreibt routing/defaults.global mit der gemappten Route', async () => {
    const { setGlobalSelection } = useEffectiveModelSelection()
    await setGlobalSelection(makeRef({ provider_connection_id: 'conn-xyz', model_id: 'gpt-4o' }))

    expect(defaultsStore.setGlobalDefault).toHaveBeenCalledWith(
      expect.objectContaining({ provider_id: 'conn-xyz', model: 'gpt-4o' }),
    )
  })

  it('setGlobalSelection schreibt active-config im Gleichschritt mit gemappten Feldern', async () => {
    const { setGlobalSelection } = useEffectiveModelSelection()
    await setGlobalSelection(makeRef({ provider_connection_id: 'conn-xyz', model_id: 'gpt-4o' }))

    expect(setActiveLlmConfigMock).toHaveBeenCalledWith({
      provider_id: 'conn-xyz',
      model: 'gpt-4o',
    })
  })

  it('setGlobalSelection schreibt Kanon (routing) VOR active-config', async () => {
    const order: string[] = []
    defaultsStore.setGlobalDefault.mockImplementation(async () => {
      order.push('routing')
    })
    setActiveLlmConfigMock.mockImplementation(async () => {
      order.push('active-config')
      return {}
    })

    const { setGlobalSelection } = useEffectiveModelSelection()
    await setGlobalSelection(makeRef())

    expect(order).toEqual(['routing', 'active-config'])
  })

  it('ensureLoaded lädt routing-defaults + connections, wenn noch nicht geladen', async () => {
    defaultsStore.hasLoadedOnce = false
    const { ensureLoaded } = useEffectiveModelSelection()
    await ensureLoaded()

    expect(defaultsStore.load).toHaveBeenCalledOnce()
    expect(providersStore.loadConnections).toHaveBeenCalledOnce()
  })

  it('ensureLoaded überspringt defaultsStore.load() idempotent, lädt connections aber weiterhin', async () => {
    defaultsStore.hasLoadedOnce = true
    const { ensureLoaded } = useEffectiveModelSelection()
    await ensureLoaded()

    expect(defaultsStore.load).not.toHaveBeenCalled()
    expect(providersStore.loadConnections).toHaveBeenCalledOnce()
  })

  it('ensureLoaded propagiert Fehler aus defaultsStore.load() nach error', async () => {
    defaultsStore.hasLoadedOnce = false
    defaultsStore.load.mockRejectedValue(new Error('routing-defaults kaputt'))
    const { ensureLoaded, error, loading } = useEffectiveModelSelection()

    await expect(ensureLoaded()).rejects.toThrow('routing-defaults kaputt')
    expect(error.value).toBe('routing-defaults kaputt')
    expect(loading.value).toBe(false)
  })

  it('ensureLoaded propagiert Fehler aus providersStore.loadConnections() nach error', async () => {
    providersStore.loadConnections.mockRejectedValue(new Error('connections kaputt'))
    const { ensureLoaded, error } = useEffectiveModelSelection()

    await expect(ensureLoaded()).rejects.toThrow('connections kaputt')
    expect(error.value).toBe('connections kaputt')
  })

  it('setGlobalSelection propagiert Fehler aus setGlobalDefault und ruft active-config NICHT auf', async () => {
    defaultsStore.setGlobalDefault.mockRejectedValue(new Error('routing-write kaputt'))
    const { setGlobalSelection, error } = useEffectiveModelSelection()

    await expect(setGlobalSelection(makeRef())).rejects.toThrow('routing-write kaputt')
    expect(error.value).toBe('routing-write kaputt')
    expect(setActiveLlmConfigMock).not.toHaveBeenCalled()
  })

  it('setGlobalSelection propagiert Fehler aus setActiveLlmConfig nach error', async () => {
    setActiveLlmConfigMock.mockRejectedValue(new Error('active-config kaputt'))
    const { setGlobalSelection, error } = useEffectiveModelSelection()

    await expect(setGlobalSelection(makeRef())).rejects.toThrow('active-config kaputt')
    expect(error.value).toBe('active-config kaputt')
  })
})
