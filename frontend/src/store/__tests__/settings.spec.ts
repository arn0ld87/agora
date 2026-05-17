import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../../api/settings', () => ({
  fetchSettings: vi.fn(),
  fetchSettingsSchema: vi.fn(),
  openSettingsStream: vi.fn(),
  putSettings: vi.fn(),
  putSecrets: vi.fn(),
}))

import {
  fetchSettings,
  fetchSettingsSchema,
  openSettingsStream,
  putSecrets,
  putSettings,
} from '../../api/settings'
import { useSettingsStore } from '../settings'

const _fetchSettings = fetchSettings as unknown as MockInstance
const _fetchSettingsSchema = fetchSettingsSchema as unknown as MockInstance
const _openSettingsStream = openSettingsStream as unknown as MockInstance
const _putSettings = putSettings as unknown as MockInstance
const _putSecrets = putSecrets as unknown as MockInstance

function buildSchemaResponse() {
  return {
    success: true,
    data: {
      sections: ['llm', 'ui', 'security'],
      fields: [
        { key: 'LLM_MODEL_NAME', section: 'llm', type: 'string', secret: false, reload_required: false, default: 'qwen2.5:32b' },
        { key: 'RUNS_POLL_INTERVAL_MS', section: 'ui', type: 'int', secret: false, reload_required: false, default: 5000, min: 1000, max: 60000 },
        { key: 'NEO4J_PASSWORD', section: 'security', type: 'string', secret: true, reload_required: true, default: null },
      ],
    },
  }
}

function buildValuesResponse({
  modelValue = 'qwen2.5:32b',
  interval = 5000,
  source = 'default',
} = {}) {
  return {
    success: true,
    data: {
      sections: ['llm', 'ui', 'security'],
      fields: {
        llm: [{
          key: 'LLM_MODEL_NAME', section: 'llm', type: 'string',
          secret: false, reload_required: false,
          value: modelValue, default: 'qwen2.5:32b',
          source, is_set: true,
        }],
        ui: [{
          key: 'RUNS_POLL_INTERVAL_MS', section: 'ui', type: 'int',
          secret: false, reload_required: false,
          value: interval, default: 5000,
          source, is_set: true,
        }],
        security: [{
          key: 'NEO4J_PASSWORD', section: 'security', type: 'string',
          secret: true, reload_required: true,
          value: null, source: 'env', is_set: true,
        }],
      },
    },
  }
}

describe('useSettingsStore', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.resetAllMocks()
  })

  it('lädt Schema + Werte und initialisiert Draft + Live-Intervall', async () => {
    _fetchSettingsSchema.mockResolvedValueOnce(buildSchemaResponse())
    _fetchSettings.mockResolvedValueOnce(buildValuesResponse({ interval: 2500 }))

    const store = useSettingsStore()
    await store.loadSettings()

    expect(store.sections).toEqual(['llm', 'ui', 'security'])
    expect(store.draft.LLM_MODEL_NAME).toBe('qwen2.5:32b')
    expect(store.draft.NEO4J_PASSWORD).toBe('')
    expect(store.runsPollIntervalMs).toBe(2500)
  })

  it('saveSettings ohne Secrets ruft nur putSettings auf', async () => {
    _fetchSettingsSchema.mockResolvedValueOnce(buildSchemaResponse())
    _fetchSettings.mockResolvedValueOnce(buildValuesResponse())
    _putSettings.mockResolvedValueOnce(buildValuesResponse({ modelValue: 'qwen2.5:14b', source: 'file' }))

    const store = useSettingsStore()
    await store.loadSettings()
    store.draft.LLM_MODEL_NAME = 'qwen2.5:14b'

    await store.saveSettings()

    expect(_putSettings).toHaveBeenCalledWith({ LLM_MODEL_NAME: 'qwen2.5:14b' })
    expect(_putSecrets).not.toHaveBeenCalled()
    expect(store.isDirty('LLM_MODEL_NAME')).toBe(false)
  })

  it('saveSettings mit Secret verlangt confirmSecrets', async () => {
    _fetchSettingsSchema.mockResolvedValueOnce(buildSchemaResponse())
    _fetchSettings.mockResolvedValueOnce(buildValuesResponse())

    const store = useSettingsStore()
    await store.loadSettings()
    store.draft.NEO4J_PASSWORD = 'new-pw'

    await expect(store.saveSettings()).rejects.toMatchObject({ code: 'confirm_secrets_required' })
    expect(_putSecrets).not.toHaveBeenCalled()
  })

  it('connectStream lädt Settings neu bei settings.changed', async () => {
    const listeners = new Map<string, (ev: MessageEvent) => void>()
    _fetchSettingsSchema.mockResolvedValue(buildSchemaResponse())
    _fetchSettings
      .mockResolvedValueOnce(buildValuesResponse({ interval: 5000 }))
      .mockResolvedValueOnce(buildValuesResponse({ interval: 1500, source: 'file' }))
    _openSettingsStream.mockImplementation(async (handlers?: { changed?: (payload: unknown) => void }) => {
      if (handlers?.changed) {
        listeners.set('settings.changed', (ev: MessageEvent) => handlers.changed?.(JSON.parse(ev.data as string)))
      }
      return { close: vi.fn() }
    })

    const store = useSettingsStore()
    await store.loadSettings()
    await store.connectStream()

    listeners.get('settings.changed')?.({
      data: JSON.stringify({
        type: 'settings.changed',
        updated_keys: ['RUNS_POLL_INTERVAL_MS'],
        ts: '2026-05-10T22:00:00Z',
      }),
    } as MessageEvent)
    await Promise.resolve()
    await Promise.resolve()

    expect(store.runsPollIntervalMs).toBe(1500)
    expect(_fetchSettings).toHaveBeenCalledTimes(2)
  })

  it('connectStream kann nach EventSource-Fehler reconnecten', async () => {
    _fetchSettingsSchema.mockResolvedValue(buildSchemaResponse())
    _fetchSettings.mockResolvedValue(buildValuesResponse())

    let errorHandler: (() => void) | undefined
    const closeSpy = vi.fn()
    _openSettingsStream
      .mockImplementationOnce(async (handlers?: { error?: () => void }) => {
        errorHandler = handlers?.error
        return { close: closeSpy }
      })
      .mockImplementationOnce(async () => ({ close: vi.fn() }))

    const store = useSettingsStore()
    await store.loadSettings()
    await store.connectStream()
    expect(store.streamState).toBe('open')

    errorHandler?.()
    expect(store.streamState).toBe('failed')
    expect(closeSpy).toHaveBeenCalledTimes(1)

    await store.connectStream()
    expect(_openSettingsStream).toHaveBeenCalledTimes(2)
    expect(store.streamState).toBe('open')
  })

  it('fieldErrors mappt Backend-Validation auf den richtigen Key', async () => {
    _fetchSettingsSchema.mockResolvedValueOnce(buildSchemaResponse())
    _fetchSettings.mockResolvedValueOnce(buildValuesResponse())
    const apiError = Object.assign(new Error('validation_failed'), {
      code: 'validation_failed',
      originalResponse: {
        success: false,
        code: 'validation_failed',
        errors: [
          { key: 'LLM_MODEL_NAME', code: 'type_error', message: 'bla' },
        ],
      },
    })
    _putSettings.mockRejectedValueOnce(apiError)

    const store = useSettingsStore()
    await store.loadSettings()
    store.draft.LLM_MODEL_NAME = 'qwen2.5:14b'

    await expect(store.saveSettings()).rejects.toBe(apiError)
    expect(store.fieldErrors('LLM_MODEL_NAME')).toEqual([
      { key: 'LLM_MODEL_NAME', code: 'type_error', message: 'bla' },
    ])
  })
})
