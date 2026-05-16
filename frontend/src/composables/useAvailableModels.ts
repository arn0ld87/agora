/**
 * useAvailableModels — Live-Provider-Discovery via ModelCatalogService.
 *
 * Pulled von /api/llm/providers (listLlmProviders) und
 * /api/llm/providers/<id>/models (listProviderModels) für jeden Provider,
 * der supports_models_endpoint === true hat.
 *
 * Liefert eine flache, sortierte Modellliste:
 *   1. provider_label alphabetisch (case-insensitive)
 *   2. model_id alphabetisch (case-insensitive)
 *
 * 5-min In-Memory-Cache pro Composable-Instanz.
 *
 * KEIN hardcoded Preset — ausschließlich Live-Discovery.
 */
import { ref, type Ref } from 'vue'
import { z } from 'zod'
import { listLlmProviders, listProviderModels } from '@/api/llmRouting'
import { ProviderDescriptorSchema } from '@/contracts/llmRoutingContract'

// ---------------------------------------------------------------------------
// Schema für eine API-Modellantwort (/api/llm/providers/<id>/models)
// ---------------------------------------------------------------------------
const ModelEntrySchema = z.object({
  id: z.string(),
  name: z.string(),
  provider_id: z.string(),
  source: z.enum(['live', 'cached', 'fallback', 'custom']),
  refreshed_at: z.number(),
})

const ModelEntryArraySchema = z.array(ModelEntrySchema)

// ---------------------------------------------------------------------------
// Öffentlicher Shape: normalisierte Picker-Einheit
// ---------------------------------------------------------------------------
export interface PickerModel {
  provider_id: string
  provider_label: string
  model_id: string
  model_label: string
  source: 'live' | 'cached' | 'fallback' | 'custom'
}

// ---------------------------------------------------------------------------
// Cache-Eintrag pro Instanz
// ---------------------------------------------------------------------------
const CACHE_TTL_MS = 5 * 60 * 1000

interface CacheEntry {
  data: PickerModel[]
  fetchedAt: number
}

export interface UseAvailableModelsReturn {
  models: Ref<PickerModel[]>
  loading: Ref<boolean>
  error: Ref<string | null>
  refresh: () => Promise<void>
}

export function useAvailableModels(): UseAvailableModelsReturn {
  const models = ref<PickerModel[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Cache liegt im Closure, lebt mit der Composable-Instanz.
  let _cache: CacheEntry | null = null

  async function refresh(): Promise<void> {
    // Cache-Prüfung
    if (_cache && Date.now() - _cache.fetchedAt < CACHE_TTL_MS) {
      models.value = _cache.data
      return
    }

    loading.value = true
    error.value = null

    try {
      // 1. Provider-Liste holen + Zod-validieren
      const rawProviders = await listLlmProviders()
      const providersResult = z.array(ProviderDescriptorSchema).safeParse(rawProviders)
      if (!providersResult.success) {
        error.value = `Provider-Schema ungültig: ${providersResult.error.issues.map((i) => i.message).join(', ')}`
        return
      }
      const providers = providersResult.data

      // 2. Nur Provider mit supports_models_endpoint anfragen
      const eligible = providers.filter((p) => p.supports_models_endpoint)

      // 3. Parallel für jeden eligible Provider Modelle laden
      const settled = await Promise.allSettled(
        eligible.map(async (provider) => {
          const raw = await listProviderModels(provider.id, provider.base_url ?? undefined)
          const result = ModelEntryArraySchema.safeParse(raw)
          if (!result.success) {
            // Einzelner Provider-Fehler wird geloggt, aber kein globaler Fehler
            console.warn(
              `[useAvailableModels] Provider "${provider.id}" Schema-Fehler:`,
              result.error.issues,
            )
            return [] as PickerModel[]
          }
          return result.data.map(
            (m): PickerModel => ({
              provider_id: provider.id,
              provider_label: provider.label,
              model_id: m.id,
              model_label: m.name || m.id,
              source: m.source,
            }),
          )
        }),
      )

      // 4. Ergebnisse zusammenführen; abgelehnte Promises loggen
      const merged: PickerModel[] = []
      for (let i = 0; i < settled.length; i++) {
        const s = settled[i]
        if (s.status === 'fulfilled') {
          merged.push(...s.value)
        } else {
          console.warn(
            `[useAvailableModels] Provider "${eligible[i].id}" fetch fehlgeschlagen:`,
            s.reason,
          )
        }
      }

      // 5. Sortierung: provider_label ASC (ci), dann model_id ASC (ci).
      // localeCompare statt ``< : 1 ; 1`` — letzteres verletzt die Komparator-
      // Konvention (0 für gleiche Werte) und ist auf manchen JS-Engines
      // instabil (Gemini-Finding).
      merged.sort((a, b) => {
        const providerCmp = a.provider_label.localeCompare(b.provider_label, undefined, { sensitivity: 'base' })
        if (providerCmp !== 0) return providerCmp
        return a.model_id.localeCompare(b.model_id, undefined, { sensitivity: 'base' })
      })

      _cache = { data: merged, fetchedAt: Date.now() }
      models.value = merged
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      error.value = msg
      console.error('[useAvailableModels] fetch error:', msg)
    } finally {
      loading.value = false
    }
  }

  // Initialer Fetch beim ersten Aufruf
  void refresh()

  return { models, loading, error, refresh }
}
