/**
 * apiKeys — Pinia-Store für API-Schlüssel-Verwaltung.
 *
 * Slice G2 — Frontend-Anteil.
 * lastCreatedToken wird NIEMALS persistiert (nur im JS-Heap).
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  type ApiKeyModel,
  type ApiKeyScope,
} from '../contracts/apiKeysContract'
import { listApiKeys, createApiKey, revokeApiKey } from '../api/apiKeys'

export const useApiKeysStore = defineStore('apiKeys', () => {
  const items = ref<ApiKeyModel[]>([])
  const loading = ref(false)
  const creating = ref(false)
  const error = ref<string | null>(null)
  // Klartext-Token: erscheint nur einmal nach POST, niemals in localStorage o.ä.
  const lastCreatedToken = ref<string | null>(null)

  async function list(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const result = await listApiKeys()
      items.value = result.items
    } catch (err) {
      const e = err as Error
      error.value = e?.message ?? 'Fehler beim Laden der API-Schlüssel.'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function create(label: string, scopes: ApiKeyScope[]): Promise<void> {
    creating.value = true
    error.value = null
    try {
      const result = await createApiKey({ label, scopes })
      lastCreatedToken.value = result.token
      items.value = [result.key, ...items.value]
    } catch (err) {
      const e = err as Error
      error.value = e?.message ?? 'Fehler beim Anlegen des API-Schlüssels.'
      throw err
    } finally {
      creating.value = false
    }
  }

  async function revoke(id: string): Promise<void> {
    error.value = null
    try {
      const revoked = await revokeApiKey(id)
      const idx = items.value.findIndex((k) => k.id === id)
      if (idx !== -1) {
        items.value = [
          ...items.value.slice(0, idx),
          revoked,
          ...items.value.slice(idx + 1),
        ]
      }
    } catch (err) {
      const e = err as Error
      error.value = e?.message ?? 'Fehler beim Widerrufen des API-Schlüssels.'
      throw err
    }
  }

  function clearLastCreatedToken(): void {
    lastCreatedToken.value = null
  }

  return {
    items,
    loading,
    creating,
    error,
    lastCreatedToken,
    list,
    create,
    revoke,
    clearLastCreatedToken,
  }
})
