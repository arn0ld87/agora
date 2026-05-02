// Issue #133 / SUB4 — Settings-Store-Tests.
//
// Decken:
//  1. loadSettings parallelisiert Schema + Werte und bringt den Draft
//     auf den serverseitigen Wert (mit leerem Draft für Secrets).
//  2. dirty-Tracking erkennt geänderte Felder; Secrets gelten dirty,
//     sobald irgendwas eingetippt wurde.
//  3. dirtySectionFlags markiert die Sektion mit einem dirty Field.
//  4. saveSettings ohne Secrets ruft nur PUT /api/settings auf.
//  5. saveSettings mit Secrets wirft synchron ohne confirmSecrets,
//     ruft mit confirmSecrets sowohl PUT als auch PUT /secrets auf.
//  6. fieldErrors mappt Backend-Validation auf den richtigen Key.
//  7. discardChanges resettet den Draft auf den serverseitigen Wert.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/settings', () => ({
  fetchSettings: vi.fn(),
  fetchSettingsSchema: vi.fn(),
  putSettings: vi.fn(),
  putSecrets: vi.fn(),
}))

import {
  fetchSettings,
  fetchSettingsSchema,
  putSecrets,
  putSettings,
} from '../../api/settings'
import settingsStore, {
  discardChanges,
  dirtyKeys,
  dirtySectionFlags,
  fieldErrors,
  isDirty,
  loadSettings,
  saveSettings,
} from '../settings'


function buildSchemaResponse() {
  return {
    data: {
      success: true,
      data: {
        sections: ['llm', 'security'],
        fields: [
          { key: 'LLM_MODEL_NAME', section: 'llm', type: 'string',
            secret: false, reload_required: false, default: 'qwen2.5:32b' },
          { key: 'NEO4J_PASSWORD', section: 'security', type: 'string',
            secret: true, reload_required: true, default: null },
        ],
      },
    },
  }
}


function buildValuesResponse({ modelValue = 'qwen2.5:32b', source = 'default' } = {}) {
  return {
    data: {
      success: true,
      data: {
        sections: ['llm', 'security'],
        fields: {
          llm: [{
            key: 'LLM_MODEL_NAME', section: 'llm', type: 'string',
            secret: false, reload_required: false,
            value: modelValue, default: 'qwen2.5:32b',
            source, is_set: true,
          }],
          security: [{
            key: 'NEO4J_PASSWORD', section: 'security', type: 'string',
            secret: true, reload_required: true,
            value: null, source: 'env', is_set: true,
          }],
        },
      },
    },
  }
}


beforeEach(() => {
  vi.resetAllMocks()
  // Singleton zurücksetzen: alle observable Felder auf Defaults
  Object.assign(settingsStore, {
    loading: false,
    saving: false,
    loadError: null,
    saveError: null,
    sections: [],
    schema: [],
    fields: {},
    draft: {},
    drafts_secret_filled: {},
    validationErrors: [],
  })
})

afterEach(() => {
  vi.resetAllMocks()
})


describe('loadSettings', () => {
  it('lädt Schema + Werte parallel und initialisiert den Draft', async () => {
    fetchSettingsSchema.mockResolvedValueOnce(buildSchemaResponse())
    fetchSettings.mockResolvedValueOnce(buildValuesResponse())

    await loadSettings()

    expect(fetchSettingsSchema).toHaveBeenCalledTimes(1)
    expect(fetchSettings).toHaveBeenCalledTimes(1)
    expect(settingsStore.sections).toEqual(['llm', 'security'])
    // Non-secret Draft = serverseitiger Wert
    expect(settingsStore.draft.LLM_MODEL_NAME).toBe('qwen2.5:32b')
    // Secret Draft = leer (Klartext kommt nicht vom Backend)
    expect(settingsStore.draft.NEO4J_PASSWORD).toBe('')
  })

  it('setzt loadError und wirft, wenn der Fetch scheitert', async () => {
    const err = new Error('boom')
    fetchSettingsSchema.mockRejectedValueOnce(err)
    fetchSettings.mockResolvedValueOnce(buildValuesResponse())

    await expect(loadSettings()).rejects.toBe(err)
    expect(settingsStore.loadError).toContain('boom')
  })
})


describe('dirty-Tracking', () => {
  beforeEach(async () => {
    fetchSettingsSchema.mockResolvedValueOnce(buildSchemaResponse())
    fetchSettings.mockResolvedValueOnce(buildValuesResponse())
    await loadSettings()
  })

  it('non-secret Field wird dirty, wenn der Draft abweicht', () => {
    expect(isDirty('LLM_MODEL_NAME')).toBe(false)
    settingsStore.draft.LLM_MODEL_NAME = 'qwen2.5:14b'
    expect(isDirty('LLM_MODEL_NAME')).toBe(true)
  })

  it('Secret-Field wird dirty, sobald der Draft nicht-leer ist', () => {
    expect(isDirty('NEO4J_PASSWORD')).toBe(false)
    settingsStore.draft.NEO4J_PASSWORD = 'new-pw'
    expect(isDirty('NEO4J_PASSWORD')).toBe(true)
  })

  it('dirtyKeys + dirtySectionFlags reflektieren Änderungen pro Sektion', () => {
    settingsStore.draft.LLM_MODEL_NAME = 'qwen2.5:14b'
    expect(dirtyKeys()).toEqual(['LLM_MODEL_NAME'])
    expect(dirtySectionFlags()).toEqual({ llm: true, security: false })
  })
})


describe('saveSettings', () => {
  beforeEach(async () => {
    fetchSettingsSchema.mockResolvedValueOnce(buildSchemaResponse())
    fetchSettings.mockResolvedValueOnce(buildValuesResponse())
    await loadSettings()
  })

  it('ruft nur putSettings, wenn nur non-secret dirty ist', async () => {
    settingsStore.draft.LLM_MODEL_NAME = 'qwen2.5:14b'
    putSettings.mockResolvedValueOnce(buildValuesResponse({ modelValue: 'qwen2.5:14b', source: 'file' }))

    await saveSettings()

    expect(putSettings).toHaveBeenCalledWith({ LLM_MODEL_NAME: 'qwen2.5:14b' })
    expect(putSecrets).not.toHaveBeenCalled()
    // Server-Snapshot wird übernommen
    expect(settingsStore.fields.llm[0].source).toBe('file')
    // Draft ist nach Save wieder im Sync mit dem Server
    expect(isDirty('LLM_MODEL_NAME')).toBe(false)
  })

  it('wirft confirm_secrets_required, wenn Secret-Save ohne confirmSecrets', async () => {
    settingsStore.draft.NEO4J_PASSWORD = 'new-pw'

    await expect(saveSettings()).rejects.toMatchObject({
      code: 'confirm_secrets_required',
    })
    expect(putSecrets).not.toHaveBeenCalled()
    expect(putSettings).not.toHaveBeenCalled()
  })

  it('mit confirmSecrets ruft sowohl putSettings als auch putSecrets', async () => {
    settingsStore.draft.LLM_MODEL_NAME = 'qwen2.5:14b'
    settingsStore.draft.NEO4J_PASSWORD = 'new-pw'
    putSettings.mockResolvedValueOnce(buildValuesResponse())
    putSecrets.mockResolvedValueOnce(buildValuesResponse())

    await saveSettings({ confirmSecrets: true })

    expect(putSettings).toHaveBeenCalledTimes(1)
    expect(putSecrets).toHaveBeenCalledTimes(1)
    expect(putSecrets).toHaveBeenCalledWith({ NEO4J_PASSWORD: 'new-pw' })
  })

  it('extrahiert Backend-Validation-Errors in fieldErrors()', async () => {
    settingsStore.draft.LLM_MODEL_NAME = 'qwen2.5:14b'
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
    putSettings.mockRejectedValueOnce(apiError)

    await expect(saveSettings()).rejects.toBe(apiError)
    const errs = fieldErrors('LLM_MODEL_NAME')
    expect(errs).toHaveLength(1)
    expect(errs[0].code).toBe('type_error')
  })
})


describe('discardChanges', () => {
  it('setzt den Draft zurück und räumt validationErrors', async () => {
    fetchSettingsSchema.mockResolvedValueOnce(buildSchemaResponse())
    fetchSettings.mockResolvedValueOnce(buildValuesResponse())
    await loadSettings()
    settingsStore.draft.LLM_MODEL_NAME = 'qwen2.5:14b'
    settingsStore.validationErrors = [
      { key: 'LLM_MODEL_NAME', code: 'x', message: 'y' },
    ]

    discardChanges()

    expect(settingsStore.draft.LLM_MODEL_NAME).toBe('qwen2.5:32b')
    expect(settingsStore.validationErrors).toEqual([])
  })
})
