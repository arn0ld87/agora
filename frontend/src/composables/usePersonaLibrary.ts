/**
 * usePersonaLibrary — Composable für Persona-Library + CRUD-Aktionen (Sub-Slice 39, Refs #203).
 *
 * Extrahiert aus Step2EnvSetup.vue (Zeilen 76–278).
 *
 * Kapselt:
 *   - Library-State (personaTemplates, isLoadingPersonaLibrary, personaLibraryError)
 *   - Manual-Editor-State (showAddPersonaModal, newPersona, isSavingPersona)
 *   - Tracking-Sets (savingPersonaKeys, usingPersonaTemplateIds)
 *   - Helpers (profileKey, profilePayload)
 *   - Actions: resetNewPersona, submitNewPersona, loadPersonaLibrary, savePersona,
 *              saveAllPersonas, usePersonaTemplate, removePersonaTemplate, removePersona
 *
 * `simulationId`, `profiles`, `fetchProfilesRealtime`, `addLog` werden als Dependencies injiziert.
 * `confirmFn` ist optional — Default: globalThis.confirm (überschreibbar für Tests).
 */

import { ref, type Ref } from 'vue'
import {
  addSimulationProfile,
  deleteSimulationProfile,
  listPersonaTemplates,
  savePersonaTemplate,
  deletePersonaTemplate,
} from '../api/simulation'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PERSONA_PAYLOAD_WHITELIST = [
  'username', 'name', 'bio', 'persona', 'age', 'gender', 'mbti', 'country',
  'profession', 'interested_topics', 'source_entity_uuid', 'source_entity_type',
  'language', 'activity_level', 'time_zone', 'location', 'verified',
] as const

const NEW_PERSONA_DEFAULT = {
  username: '', name: '', bio: '', persona: '',
  profession: '', country: 'DE', age: null as string | number | null,
  gender: 'other', mbti: '', interested_topics: '',
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UsePersonaLibraryDeps {
  simulationId: Ref<string | null | undefined>
  profiles: Ref<unknown[]>
  fetchProfilesRealtime: () => Promise<void> | void
  addLog: (msg: string) => void
  /** Optional confirm-Override für Tests; default: globalThis.confirm */
  confirmFn?: (msg: string) => boolean
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function usePersonaLibrary(deps: UsePersonaLibraryDeps) {
  const { simulationId, profiles, fetchProfilesRealtime, addLog } = deps
  const confirm = deps.confirmFn ?? ((msg: string) => globalThis.confirm(msg))

  // --- Library State ---

  const personaTemplates = ref<unknown[]>([])
  const isLoadingPersonaLibrary = ref(false)
  const personaLibraryError = ref('')
  const savingPersonaKeys = ref<Set<string>>(new Set())
  const usingPersonaTemplateIds = ref<Set<string>>(new Set())

  // --- Manual Editor State ---

  const showAddPersonaModal = ref(false)
  const newPersona = ref<{
    username: string
    name: string
    bio: string
    persona: string
    profession: string
    country: string
    age: string | number | null
    gender: string
    mbti: string
    interested_topics: string
  }>({ ...NEW_PERSONA_DEFAULT })
  const isSavingPersona = ref(false)

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function profileKey(profile: Record<string, unknown> | null | undefined): string {
    return String(profile?.template_id || profile?.username || profile?.name || profile?.user_id || '')
  }

  function profilePayload(profile: Record<string, unknown> | null | undefined): Record<string, unknown> {
    const payload: Record<string, unknown> = {}
    for (const field of PERSONA_PAYLOAD_WHITELIST) {
      const value = profile?.[field]
      if (value !== undefined && value !== null && value !== '') payload[field] = value
    }
    return payload
  }

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  function resetNewPersona(): void {
    newPersona.value = { ...NEW_PERSONA_DEFAULT }
  }

  async function submitNewPersona(): Promise<void> {
    if (!simulationId.value) return
    const data: Record<string, unknown> = { ...newPersona.value }
    // topics: comma-separated -> array
    if (typeof data.interested_topics === 'string') {
      data.interested_topics = (data.interested_topics as string)
        .split(',').map((s: string) => s.trim()).filter(Boolean)
    }
    if (data.age === '' || data.age == null) delete data.age
    isSavingPersona.value = true
    try {
      const res = await addSimulationProfile(simulationId.value, data as never)
      const envelope = res as unknown as { success?: boolean; data?: { profile?: { username?: string } }; error?: string }
      if (envelope?.success) {
        addLog(`Persona hinzugefügt: ${envelope.data?.profile?.username}`)
        await fetchProfilesRealtime()
        showAddPersonaModal.value = false
        resetNewPersona()
      } else {
        addLog(`Fehler: ${envelope?.error || 'unbekannt'}`)
      }
    } catch (err) {
      addLog((err as Error).message)
    } finally {
      isSavingPersona.value = false
    }
  }

  async function loadPersonaLibrary(): Promise<void> {
    isLoadingPersonaLibrary.value = true
    personaLibraryError.value = ''
    try {
      const res = await listPersonaTemplates()
      const envelope = res as unknown as { success?: boolean; data?: { templates?: unknown[] }; error?: string }
      if (envelope?.success && Array.isArray(envelope.data?.templates)) {
        personaTemplates.value = envelope.data.templates
      } else {
        personaLibraryError.value = envelope?.error || 'Bibliothek konnte nicht geladen werden.'
      }
    } catch (err) {
      personaLibraryError.value = (err as Error).message
    } finally {
      isLoadingPersonaLibrary.value = false
    }
  }

  async function savePersona(profile: Record<string, unknown>): Promise<void> {
    const key = profileKey(profile)
    if (!key) return
    savingPersonaKeys.value = new Set([...savingPersonaKeys.value, key])
    try {
      const res = await savePersonaTemplate(profilePayload(profile) as never)
      const envelope = res as unknown as { success?: boolean; data?: { template?: { name?: string; username?: string } }; error?: string }
      if (envelope?.success) {
        addLog(`Persona gespeichert: ${envelope.data?.template?.name || envelope.data?.template?.username || key}`)
        await loadPersonaLibrary()
      } else {
        addLog(`Fehler: ${envelope?.error || 'unbekannt'}`)
      }
    } catch (err) {
      addLog((err as Error).message)
    } finally {
      const next = new Set(savingPersonaKeys.value)
      next.delete(key)
      savingPersonaKeys.value = next
    }
  }

  async function saveAllPersonas(): Promise<void> {
    for (const profile of profiles.value) {
      await savePersona(profile as Record<string, unknown>)
    }
  }

  async function usePersonaTemplate(template: Record<string, unknown>): Promise<void> {
    if (!simulationId.value || !template?.template_id) return
    const templateId = template.template_id as string
    usingPersonaTemplateIds.value = new Set([...usingPersonaTemplateIds.value, templateId])
    try {
      const payload = {
        ...profilePayload(template),
        source_entity_type: 'library',
      }
      const res = await addSimulationProfile(simulationId.value, payload as never)
      const envelope = res as unknown as { success?: boolean; data?: { profile?: { username?: string } }; error?: string }
      if (envelope?.success) {
        addLog(`Persona wiederverwendet: ${envelope.data?.profile?.username}`)
        await fetchProfilesRealtime()
      } else {
        addLog(`Fehler: ${envelope?.error || 'unbekannt'}`)
      }
    } catch (err) {
      addLog((err as Error).message)
    } finally {
      const next = new Set(usingPersonaTemplateIds.value)
      next.delete(templateId)
      usingPersonaTemplateIds.value = next
    }
  }

  async function removePersonaTemplate(templateId: string): Promise<void> {
    if (!templateId) return
    if (!confirm('Gespeicherte Persona wirklich löschen?')) return
    try {
      const res = await deletePersonaTemplate(templateId)
      const envelope = res as { success?: boolean; error?: string }
      if (envelope?.success) await loadPersonaLibrary()
      else addLog(`Fehler: ${envelope?.error || 'unbekannt'}`)
    } catch (err) {
      addLog((err as Error).message)
    }
  }

  async function removePersona(username: string): Promise<void> {
    if (!simulationId.value || !username) return
    if (!confirm(`Persona "${username}" löschen?`)) return
    try {
      const res = await deleteSimulationProfile(simulationId.value, username)
      const envelope = res as { success?: boolean; error?: string }
      if (envelope?.success) {
        addLog(`Persona gelöscht: ${username}`)
        await fetchProfilesRealtime()
      } else {
        addLog(`Fehler: ${envelope?.error || 'unbekannt'}`)
      }
    } catch (err) {
      addLog((err as Error).message)
    }
  }

  // ---------------------------------------------------------------------------
  // Return
  // ---------------------------------------------------------------------------

  return {
    // state
    personaTemplates,
    isLoadingPersonaLibrary,
    personaLibraryError,
    savingPersonaKeys,
    usingPersonaTemplateIds,
    showAddPersonaModal,
    newPersona,
    isSavingPersona,
    // helpers
    profileKey,
    profilePayload,
    // actions
    resetNewPersona,
    submitNewPersona,
    loadPersonaLibrary,
    savePersona,
    saveAllPersonas,
    usePersonaTemplate,
    removePersonaTemplate,
    removePersona,
  }
}
