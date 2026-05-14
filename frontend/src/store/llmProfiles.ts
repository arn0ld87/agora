/**
 * llmProfiles — Pinia-Store für LLM-Profil-Verwaltung.
 *
 * P5.4 — Frontend-Anteil.
 * Composition-API-Style analog zu store/apiKeys.ts.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { LlmProfile, LlmProfileCreateRequest } from '../contracts/llmProfileContract'
import {
  fetchLlmProfiles,
  createLlmProfile,
  updateLlmProfile,
  deleteLlmProfile,
  setDefaultLlmProfile,
} from '../api/llmProfiles'

export const useLlmProfilesStore = defineStore('llmProfiles', () => {
  const profiles = ref<LlmProfile[]>([])
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)

  async function fetch(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      profiles.value = await fetchLlmProfiles()
    } catch (err) {
      const e = err as Error
      error.value = e?.message ?? 'Fehler beim Laden der LLM-Profile.'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function create(req: LlmProfileCreateRequest): Promise<void> {
    saving.value = true
    error.value = null
    try {
      const created = await createLlmProfile(req)
      profiles.value = [created, ...profiles.value]
    } catch (err) {
      const e = err as Error
      error.value = e?.message ?? 'Fehler beim Anlegen des Profils.'
      throw err
    } finally {
      saving.value = false
    }
  }

  async function update(id: string, req: LlmProfileCreateRequest): Promise<void> {
    saving.value = true
    error.value = null
    try {
      const updated = await updateLlmProfile(id, req)
      const idx = profiles.value.findIndex((p) => p.id === id)
      if (idx !== -1) {
        profiles.value = [
          ...profiles.value.slice(0, idx),
          updated,
          ...profiles.value.slice(idx + 1),
        ]
      }
    } catch (err) {
      const e = err as Error
      error.value = e?.message ?? 'Fehler beim Aktualisieren des Profils.'
      throw err
    } finally {
      saving.value = false
    }
  }

  async function remove(id: string): Promise<void> {
    saving.value = true
    error.value = null
    try {
      await deleteLlmProfile(id)
      profiles.value = profiles.value.filter((p) => p.id !== id)
    } catch (err) {
      const e = err as Error
      error.value = e?.message ?? 'Fehler beim Löschen des Profils.'
      throw err
    } finally {
      saving.value = false
    }
  }

  async function setDefault(id: string): Promise<void> {
    saving.value = true
    error.value = null
    try {
      const updated = await setDefaultLlmProfile(id)
      // Alle is_default lokal zurücksetzen, dann das zurückgegebene ersetzen.
      const reset = profiles.value.map((p) => ({ ...p, is_default: false }))
      const idx = reset.findIndex((p) => p.id === id)
      if (idx !== -1) {
        profiles.value = [
          ...reset.slice(0, idx),
          updated,
          ...reset.slice(idx + 1),
        ]
      } else {
        profiles.value = reset
      }
    } catch (err) {
      const e = err as Error
      error.value = e?.message ?? 'Fehler beim Setzen des Standard-Profils.'
      throw err
    } finally {
      saving.value = false
    }
  }

  return {
    profiles,
    loading,
    saving,
    error,
    fetch,
    create,
    update,
    remove,
    setDefault,
  }
})
