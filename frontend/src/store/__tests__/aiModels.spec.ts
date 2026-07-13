/**
 * aiModels — konsolidierter Store, Vitest-Specs (Sub-Slice 5.5).
 *
 * Deckt die drei zusammengeführten Teil-Stores (llmProviders, llmProfiles,
 * llmRoutingDefaults) plus die neue Facade ``useAiModelsStore`` ab. Der Fokus
 * liegt auf der Konsolidierung: unveränderte Store-IDs, stabile Public-API und
 * die gebündelte Facade — nicht auf Re-Test jeder Legacy-Verzweigung.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// Mock aller API-Module — keine echten HTTP-Calls.
vi.mock('../../api/llmRouting', () => ({ listLlmProviders: vi.fn() }))
vi.mock('../../api/llmProviderKeys', () => ({
  deleteLlmProviderKey: vi.fn(),
  listLlmProviderKeys: vi.fn(),
  upsertLlmProviderKey: vi.fn(),
  testLlmProvider: vi.fn(),
}))
vi.mock('../../api/providerConnections', () => ({
  deleteProviderConnection: vi.fn(),
  listProviderConnectionModels: vi.fn(),
  listProviderConnections: vi.fn(),
  testProviderConnection: vi.fn(),
  upsertProviderConnection: vi.fn(),
}))
vi.mock('../../api/llmProfiles', () => ({
  fetchLlmProfiles: vi.fn(),
  createLlmProfile: vi.fn(),
  updateLlmProfile: vi.fn(),
  deleteLlmProfile: vi.fn(),
  setDefaultLlmProfile: vi.fn(),
}))
vi.mock('../../api/llmRoutingDefaults', () => ({
  getRoutingDefaults: vi.fn(),
  patchRoutingDefaultStage: vi.fn(),
  replaceGlobalDefault: vi.fn(),
  replaceRoutingDefaults: vi.fn(),
}))

import { listLlmProviders } from '../../api/llmRouting'
import { listLlmProviderKeys } from '../../api/llmProviderKeys'
import {
  listProviderConnections,
  upsertProviderConnection,
  deleteProviderConnection,
  testProviderConnection,
} from '../../api/providerConnections'
import {
  fetchLlmProfiles,
  createLlmProfile,
  setDefaultLlmProfile,
} from '../../api/llmProfiles'
import {
  getRoutingDefaults,
  replaceGlobalDefault,
  patchRoutingDefaultStage,
} from '../../api/llmRoutingDefaults'

import {
  useLlmProvidersStore,
  useLlmProfilesStore,
  useLlmRoutingDefaultsStore,
  useAiModelsStore,
} from '../aiModels'

import type { ProviderConnection, ProviderConnectionTestResult } from '../../contracts/aiProviderContract'
import type { LlmProfile } from '../../contracts/llmProfileContract'
import type { StageLLMRoute } from '../../contracts/llmRoutingContract'
import type { WorkspaceLlmRoutingDefaults } from '../../contracts/workspaceRoutingContract'

type MockFn = ReturnType<typeof vi.fn>
const mock = (fn: unknown): MockFn => fn as unknown as MockFn

// --- Fixtures (nur die vom Store gelesenen Felder; Store validiert nicht) ---
function makeConnection(overrides: Partial<ProviderConnection> = {}): ProviderConnection {
  return {
    id: 'conn-ollama',
    provider_kind: 'ollama',
    display_name: 'Ollama lokal',
    status: 'connected',
    enabled: true,
    ...overrides,
  } as ProviderConnection
}

function makeProfile(overrides: Partial<LlmProfile> = {}): LlmProfile {
  return {
    id: 'profile-1',
    name: 'Standard',
    is_default: false,
    ...overrides,
  } as LlmProfile
}

function makeRoute(overrides: Partial<StageLLMRoute> = {}): StageLLMRoute {
  return {
    stage: null,
    provider_id: 'ollama',
    model: 'qwen3',
    temperature: null,
    max_tokens: null,
    reasoning_effort: 'none',
    provider_options: {},
    ...overrides,
  } as StageLLMRoute
}

function makeDefaults(overrides: Partial<WorkspaceLlmRoutingDefaults> = {}): WorkspaceLlmRoutingDefaults {
  return {
    global_default: makeRoute(),
    stage_overrides: {},
    version: 1,
    updated_at: '2026-07-13T00:00:00Z',
    ...overrides,
  } as WorkspaceLlmRoutingDefaults
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('aiModels — llmProviders-Teil', () => {
  it('behält die Pinia-Store-ID "llmProviders"', () => {
    expect(useLlmProvidersStore().$id).toBe('llmProviders')
  })

  it('loadProviders() füllt providers + entries', async () => {
    mock(listLlmProviders).mockResolvedValue([{ id: 'ollama', label: 'Ollama' }])
    mock(listLlmProviderKeys).mockResolvedValue({ items: [{ provider_id: 'ollama', base_url: 'http://x' }] })
    const store = useLlmProvidersStore()
    await store.loadProviders()
    expect(store.providers).toHaveLength(1)
    expect(store.hasKey('ollama')).toBe(true)
  })

  it('loadConnections() mappt items nach id', async () => {
    mock(listProviderConnections).mockResolvedValue({ items: [makeConnection()] })
    const store = useLlmProvidersStore()
    await store.loadConnections()
    expect(store.connections['conn-ollama']?.provider_kind).toBe('ollama')
    expect(store.isConnectionConfigured('conn-ollama')).toBe(true)
  })

  it('upsertConnection() speichert Connection und räumt busy ab', async () => {
    const conn = makeConnection({ id: 'conn-new' })
    mock(upsertProviderConnection).mockResolvedValue(conn)
    const store = useLlmProvidersStore()
    await store.upsertConnection('conn-new', { display_name: 'X', provider_kind: 'ollama', enabled: true })
    expect(store.connections['conn-new']).toEqual(conn)
    expect(store.connectionBusy['conn-new']).toBe(false)
  })

  it('removeConnection() löscht die Connection', async () => {
    mock(listProviderConnections).mockResolvedValue({ items: [makeConnection()] })
    mock(deleteProviderConnection).mockResolvedValue(undefined)
    const store = useLlmProvidersStore()
    await store.loadConnections()
    await store.removeConnection('conn-ollama')
    expect(store.connections['conn-ollama']).toBeUndefined()
  })

  it('testConnection() speichert Ergebnis und lädt Connections neu', async () => {
    const result = { status: 'available', models_found: 3 } as unknown as ProviderConnectionTestResult
    mock(testProviderConnection).mockResolvedValue(result)
    mock(listProviderConnections).mockResolvedValue({ items: [makeConnection()] })
    const store = useLlmProvidersStore()
    await store.testConnection('conn-ollama')
    expect(store.connectionTestResults['conn-ollama']).toEqual(result)
    expect(mock(listProviderConnections)).toHaveBeenCalled()
  })

  it('markiert provider_unsupported ehrlich statt Verbindung vorzutäuschen', async () => {
    const err = Object.assign(new Error('nope'), { code: 'provider_unsupported', __isApiError: true })
    mock(upsertProviderConnection).mockRejectedValue(err)
    const store = useLlmProvidersStore()
    await expect(
      store.upsertConnection('conn-copilot', { display_name: 'Copilot', provider_kind: 'github_copilot', enabled: true }),
    ).rejects.toThrow()
    expect(store.connectionError['conn-copilot']).toContain('nope')
  })
})

describe('aiModels — llmProfiles-Teil', () => {
  it('behält die Pinia-Store-ID "llmProfiles"', () => {
    expect(useLlmProfilesStore().$id).toBe('llmProfiles')
  })

  it('fetch() füllt profiles', async () => {
    mock(fetchLlmProfiles).mockResolvedValue([makeProfile()])
    const store = useLlmProfilesStore()
    await store.fetch()
    expect(store.profiles).toHaveLength(1)
    expect(store.error).toBeNull()
  })

  it('create() stellt das neue Profil an den Anfang', async () => {
    const store = useLlmProfilesStore()
    store.profiles = [makeProfile({ id: 'old' })]
    mock(createLlmProfile).mockResolvedValue(makeProfile({ id: 'new' }))
    await store.create({ name: 'Neu' } as never)
    expect(store.profiles[0]?.id).toBe('new')
    expect(store.profiles).toHaveLength(2)
  })

  it('setDefault() setzt genau ein is_default', async () => {
    const store = useLlmProfilesStore()
    store.profiles = [makeProfile({ id: 'a', is_default: true }), makeProfile({ id: 'b' })]
    mock(setDefaultLlmProfile).mockResolvedValue(makeProfile({ id: 'b', is_default: true }))
    await store.setDefault('b')
    expect(store.profiles.filter((p) => p.is_default)).toHaveLength(1)
    expect(store.profiles.find((p) => p.id === 'b')?.is_default).toBe(true)
  })

  it('setzt error bei API-Fehler', async () => {
    mock(fetchLlmProfiles).mockRejectedValue(new Error('boom'))
    const store = useLlmProfilesStore()
    await expect(store.fetch()).rejects.toThrow('boom')
    expect(store.error).toBe('boom')
  })
})

describe('aiModels — llmRoutingDefaults-Teil', () => {
  it('behält die Pinia-Store-ID "llmRoutingDefaults"', () => {
    expect(useLlmRoutingDefaultsStore().$id).toBe('llmRoutingDefaults')
  })

  it('load() setzt defaults + hasLoadedOnce', async () => {
    mock(getRoutingDefaults).mockResolvedValue(makeDefaults())
    const store = useLlmRoutingDefaultsStore()
    await store.load()
    expect(store.globalDefault.model).toBe('qwen3')
    expect(store.hasLoadedOnce).toBe(true)
  })

  it('setGlobalDefault() aktualisiert global_default', async () => {
    const next = makeDefaults({ global_default: makeRoute({ model: 'gpt-4o' }) })
    mock(replaceGlobalDefault).mockResolvedValue(next)
    const store = useLlmRoutingDefaultsStore()
    await store.setGlobalDefault(makeRoute({ model: 'gpt-4o' }))
    expect(store.globalDefault.model).toBe('gpt-4o')
  })

  it('effectiveRouteForStage() bevorzugt Override vor Global-Default', async () => {
    const override = makeRoute({ model: 'stage-model' })
    mock(getRoutingDefaults).mockResolvedValue(
      makeDefaults({ stage_overrides: { report_generation: override } }),
    )
    const store = useLlmRoutingDefaultsStore()
    await store.load()
    expect(store.effectiveRouteForStage('report_generation').model).toBe('stage-model')
    expect(store.effectiveRouteForStage('persona_generation').model).toBe('qwen3')
  })

  it('clearStageOverride() patcht die Stage mit null', async () => {
    mock(patchRoutingDefaultStage).mockResolvedValue(makeDefaults())
    const store = useLlmRoutingDefaultsStore()
    await store.clearStageOverride('report_generation')
    expect(mock(patchRoutingDefaultStage)).toHaveBeenCalledWith('report_generation', null)
  })
})

describe('aiModels — useAiModelsStore Facade', () => {
  it('bündelt die drei Teil-Stores mit korrekten IDs', () => {
    const bundle = useAiModelsStore()
    expect(bundle.providers.$id).toBe('llmProviders')
    expect(bundle.profiles.$id).toBe('llmProfiles')
    expect(bundle.routingDefaults.$id).toBe('llmRoutingDefaults')
  })

  it('gibt dieselbe Store-Instanz wie die Einzel-Hooks zurück', () => {
    const bundle = useAiModelsStore()
    expect(bundle.providers).toBe(useLlmProvidersStore())
    expect(bundle.routingDefaults).toBe(useLlmRoutingDefaultsStore())
  })
})
