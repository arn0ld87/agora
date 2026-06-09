import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  fetchSettings,
  fetchSettingsSchema,
  openSettingsStream,
  putSecrets,
  putSettings,
} from '../api/settings'
import type { SecretsPayload } from '../api/settings'
import {
  parseSettingsChangedEvent,
  parseSettingsEnvelope,
  parseSettingsSchemaEnvelope,
  type SettingsFieldMeta,
  type SettingsFieldSpec,
} from '../contracts/settingsContract'

export interface ValidationError {
  key: string
  code: string
  message: string
}

interface SettingsApiError extends Error {
  code?: string
  originalResponse?: {
    errors?: ValidationError[]
  }
}

function resetRecord(target: Record<string, unknown>, next: Record<string, unknown> = {}): void {
  for (const key of Object.keys(target)) {
    delete target[key]
  }
  Object.assign(target, next)
}

export const useSettingsStore = defineStore('settings', () => {
  const loading = ref(false)
  const saving = ref(false)
  const loadError = ref<string | null>(null)
  const saveError = ref<string | null>(null)
  const sections = ref<string[]>([])
  const schema = ref<SettingsFieldSpec[]>([])
  const fields = ref<Record<string, SettingsFieldMeta[]>>({})
  const draft = reactive<Record<string, unknown>>({})
  const validationErrors = ref<ValidationError[]>([])
  const streamState = ref<'idle' | 'connecting' | 'open' | 'failed'>('idle')
  let eventSource: EventSource | null = null

  function _findSpec(key: string): SettingsFieldSpec | null {
    return schema.value.find((item) => item.key === key) || null
  }

  function _findFieldMeta(key: string): SettingsFieldMeta | null {
    for (const section of sections.value) {
      for (const item of fields.value[section] || []) {
        if (item.key === key) return item
      }
    }
    return null
  }

  function _resetDraftFromFields(): void {
    const nextDraft: Record<string, unknown> = {}
    for (const section of sections.value) {
      for (const item of fields.value[section] || []) {
        nextDraft[item.key] = item.secret ? '' : item.value
      }
    }
    resetRecord(draft, nextDraft)
  }

  function _applyServerState(nextSchema: SettingsFieldSpec[], nextValues: Record<string, SettingsFieldMeta[]>, nextSections: string[]): void {
    schema.value = nextSchema
    fields.value = nextValues
    sections.value = nextSections
    _resetDraftFromFields()
  }

  async function loadSettings(): Promise<void> {
    loading.value = true
    loadError.value = null
    try {
      const [schemaRes, valuesRes] = await Promise.all([
        fetchSettingsSchema(),
        fetchSettings(),
      ])
      const parsedSchema = parseSettingsSchemaEnvelope(schemaRes)
      const parsedValues = parseSettingsEnvelope(valuesRes)
      if (!parsedSchema.success) {
        throw new Error(`Schema-Drift settings/schema: ${parsedSchema.error.issues[0]?.message ?? 'unbekannt'}`)
      }
      if (!parsedValues.success) {
        throw new Error(`Schema-Drift settings: ${parsedValues.error.issues[0]?.message ?? 'unbekannt'}`)
      }
      _applyServerState(
        parsedSchema.data.data.fields,
        parsedValues.data.data.fields,
        parsedValues.data.data.sections,
      )
    } catch (err) {
      const e = err as Error
      loadError.value = e?.message || 'Fehler beim Laden der Einstellungen.'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function ensureLoaded(): Promise<void> {
    if (sections.value.length > 0 || loading.value) return
    await loadSettings()
  }

  function isDirty(key: string): boolean {
    const spec = _findSpec(key)
    if (spec?.secret) {
      return ((draft[key] as string) || '') !== ''
    }
    const meta = _findFieldMeta(key)
    if (!meta) return false
    return draft[key] !== meta.value
  }

  const dirtyKeys = computed<string[]>(() => {
    const keys: string[] = []
    for (const section of sections.value) {
      for (const item of fields.value[section] || []) {
        if (isDirty(item.key)) keys.push(item.key)
      }
    }
    return keys
  })

  const dirtySectionFlags = computed<Record<string, boolean>>(() => {
    const out: Record<string, boolean> = {}
    for (const section of sections.value) {
      out[section] = (fields.value[section] || []).some((item) => isDirty(item.key))
    }
    return out
  })

  function _splitDirtyByKind(): { nonSecrets: Record<string, unknown>; secrets: SecretsPayload } {
    const nonSecrets: Record<string, unknown> = {}
    const secrets: SecretsPayload = {}
    for (const key of dirtyKeys.value) {
      const spec = _findSpec(key)
      if (spec?.secret) {
        secrets[key] = String(draft[key] ?? '')
      } else {
        nonSecrets[key] = draft[key]
      }
    }
    return { nonSecrets, secrets }
  }

  async function saveSettings(
    { confirmSecrets = false }: { confirmSecrets?: boolean } = {},
  ): Promise<unknown> {
    saveError.value = null
    validationErrors.value = []
    const { nonSecrets, secrets } = _splitDirtyByKind()
    const hasSecrets = Object.keys(secrets).length > 0
    const hasNonSecrets = Object.keys(nonSecrets).length > 0

    if (hasSecrets && !confirmSecrets) {
      const err = Object.assign(new Error('confirm_secrets_required'), {
        code: 'confirm_secrets_required',
      })
      throw err
    }

    saving.value = true
    try {
      let lastResponse: unknown = null
      if (hasNonSecrets) {
        lastResponse = await putSettings(nonSecrets)
      }
      if (hasSecrets) {
        lastResponse = await putSecrets(secrets)
      }
      if (lastResponse) {
        const parsedValues = parseSettingsEnvelope(lastResponse)
        if (!parsedValues.success) {
          throw new Error(`Schema-Drift settings: ${parsedValues.error.issues[0]?.message ?? 'unbekannt'}`)
        }
        _applyServerState(
          schema.value,
          parsedValues.data.data.fields,
          parsedValues.data.data.sections,
        )
      }
      return lastResponse
    } catch (err) {
      const e = err as SettingsApiError
      saveError.value = e?.message || 'Fehler beim Speichern.'
      if (e?.originalResponse?.errors) {
        validationErrors.value = e.originalResponse.errors
      }
      throw err
    } finally {
      saving.value = false
    }
  }

  function discardChanges(): void {
    _resetDraftFromFields()
    validationErrors.value = []
    saveError.value = null
  }

  function fieldErrors(key: string): ValidationError[] {
    return validationErrors.value.filter((item) => item.key === key)
  }

  async function connectStream(): Promise<void> {
    if (streamState.value === 'connecting') return
    if (eventSource !== null && streamState.value === 'open') return
    streamState.value = 'connecting'
    try {
      eventSource = await openSettingsStream({
        changed: async (payload: unknown) => {
          const parsed = parseSettingsChangedEvent(payload)
          if (!parsed.success || saving.value) return
          await loadSettings()
        },
        error: (ev: Event) => {
          // openSettingsStream awaits a signed ticket, so an EventSource
          // error can fire before the outer eventSource ref is assigned.
          // The event target carries the actual EventSource — close that
          // one too, then drop the cached ref if it already pointed at us.
          if (typeof EventSource !== 'undefined' && ev.target instanceof EventSource) {
            ev.target.close()
          }
          if (eventSource) {
            eventSource.close()
            eventSource = null
          }
          streamState.value = 'failed'
        },
      })
      streamState.value = 'open'
    } catch {
      streamState.value = 'failed'
    }
  }

  function disconnectStream(): void {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    streamState.value = 'idle'
  }

  const runsPollIntervalMs = computed<number>(() => {
    const field = (fields.value.ui || []).find((item) => item.key === 'RUNS_POLL_INTERVAL_MS')
    const value = field?.value
    return typeof value === 'number' && Number.isFinite(value) ? value : 5000
  })

  return {
    loading,
    saving,
    loadError,
    saveError,
    sections,
    schema,
    fields,
    draft,
    validationErrors,
    streamState,
    dirtyKeys,
    dirtySectionFlags,
    runsPollIntervalMs,
    ensureLoaded,
    loadSettings,
    saveSettings,
    discardChanges,
    fieldErrors,
    isDirty,
    connectStream,
    disconnectStream,
  }
})
