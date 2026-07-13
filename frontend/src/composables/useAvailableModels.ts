// legacy-model-picker-allow: pre-5.5 v3 picker importer — see docs/epics/onboarding-provider-unification/slice-5-subplan.md (5.4 migrates, 5.5 removes)
/**
 * useAvailableModels — Discovery aus dem kanonischen ProviderConnectionStore.
 *
 * Der Composable adaptiert die Connection- und Modell-Metadaten einmalig auf
 * den Picker-Vertrag. Legacy-Providerlisten bleiben damit außerhalb des v4-
 * Picker-Datenpfads.
 */
import { ref, type Ref } from 'vue'
import { useLlmProvidersStore } from '@/store/llmProviders'
import type { AiCapability, AiModelRefInput, AiModelStatus, AiProviderKind } from '@/contracts/aiModelRef'
import type { AiModel, ProviderConnection } from '@/contracts/aiProviderContract'

const PICKER_CAPABILITIES = [
  'chat', 'embeddings', 'streaming', 'tool_calling', 'json_object', 'json_schema', 'vision', 'reasoning',
] as const satisfies readonly AiCapability[]

/** Legacy-kompatibler Shape für den noch getrennten v3-ModelPicker. */
export interface PickerModel {
  provider_id: string
  provider_label: string
  model_id: string
  model_label: string
  source: 'live' | 'cached' | 'fallback' | 'custom'
}

/** Vollständiger Discovery-Shape für den v4-AiModelPicker. */
export type DiscoveredPickerModel = PickerModel & AiModelRefInput

interface CacheEntry {
  data: DiscoveredPickerModel[]
  fetchedAt: number
}

export interface RefreshOptions {
  force?: boolean
}

export interface UseAvailableModelsReturn {
  models: Ref<DiscoveredPickerModel[]>
  loading: Ref<boolean>
  error: Ref<string | null>
  refresh: (options?: RefreshOptions) => Promise<void>
}

const CACHE_TTL_MS = 5 * 60 * 1000

function pickerCapabilities(model: AiModel): AiCapability[] {
  return PICKER_CAPABILITIES.filter((capability) => model.capabilities[capability] === 'supported')
}

function pickerStatus(
  connection: ProviderConnection,
  model: AiModel,
  unsupported: boolean,
): AiModelStatus {
  if (unsupported) return 'unsupported'
  if (!connection.enabled || connection.status === 'disconnected' || connection.status === 'error') {
    return 'unavailable'
  }
  if (model.status === 'unavailable' || model.status === 'deprecated') return 'unavailable'
  if (connection.status === 'degraded') return 'degraded'
  if (model.status === 'available') return 'available'
  return 'unavailable'
}

function toPickerModel(
  connection: ProviderConnection,
  model: AiModel,
  unsupported: boolean,
): DiscoveredPickerModel {
  return {
    provider_connection_id: connection.id,
    provider_kind: connection.provider_kind as AiProviderKind,
    display_name: connection.display_name,
    model_id: model.model_id,
    context_window: model.context_window ?? undefined,
    capabilities: pickerCapabilities(model),
    status: pickerStatus(connection, model, unsupported),
    local_or_cloud: model.local_or_cloud === 'local' || connection.transport === 'local' ? 'local' : 'cloud',
    provider_id: connection.id,
    provider_label: connection.display_name,
    model_label: model.display_name,
    source: model.source,
  }
}

export function useAvailableModels(): UseAvailableModelsReturn {
  const providerStore = useLlmProvidersStore()
  const models = ref<DiscoveredPickerModel[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  let cache: CacheEntry | null = null

  async function refresh({ force = false }: RefreshOptions = {}): Promise<void> {
    if (!force && cache && Date.now() - cache.fetchedAt < CACHE_TTL_MS) {
      models.value = cache.data
      return
    }

    loading.value = true
    error.value = null
    try {
      await providerStore.loadConnections()
      const connections = Object.values(providerStore.connections)
      const settled = await Promise.allSettled(
        connections.map(async (connection) => {
          const discovered = await providerStore.fetchConnectionModels(connection.id)
          return discovered.map((model) =>
            toPickerModel(connection, model, Boolean(providerStore.connectionUnsupported[connection.id])),
          )
        }),
      )

      const merged: DiscoveredPickerModel[] = []
      settled.forEach((result, index) => {
        if (result.status === 'fulfilled') {
          merged.push(...result.value)
          return
        }
        const connection = connections[index]
        console.warn(`[useAvailableModels] Connection "${connection.id}" fetch fehlgeschlagen:`, result.reason)
      })
      merged.sort((left, right) => {
        const providerOrder = left.display_name.localeCompare(right.display_name, undefined, { sensitivity: 'base' })
        return providerOrder || left.model_id.localeCompare(right.model_id, undefined, { sensitivity: 'base' })
      })
      cache = { data: merged, fetchedAt: Date.now() }
      models.value = merged
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause)
      error.value = message
      models.value = []
      console.error('[useAvailableModels] fetch error:', message)
    } finally {
      loading.value = false
    }
  }

  void refresh()
  return { models, loading, error, refresh }
}
