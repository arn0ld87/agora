import type { AiModelRefPayload } from '@/api/report'
import { getRunModelOverride } from '@/store/runModelOverride'
import { useEffectiveModelSelection } from './useEffectiveModelSelection'

export interface RunModelResolution {
  ref: AiModelRefPayload | null
  usedRunOverride: boolean
}

export function useRunModelResolver(): {
  resolveRunModel: () => Promise<RunModelResolution>
} {
  const effectiveModel = useEffectiveModelSelection()

  async function resolveRunModel(): Promise<RunModelResolution> {
    const override = getRunModelOverride()
    if (override) {
      return {
        ref: {
          provider_connection_id: override.provider_connection_id,
          model_id: override.model_id,
          source: override.source,
        },
        usedRunOverride: true,
      }
    }

    try {
      await effectiveModel.ensureLoaded()
    } catch {
      // Best effort: Ohne ladbaren Kanon entscheidet das Backend-Routing.
    }
    const effectiveRef = effectiveModel.effectiveRef.value
    return {
      ref: effectiveRef
        ? {
            provider_connection_id: effectiveRef.provider_connection_id,
            model_id: effectiveRef.model_id,
            source: effectiveRef.source,
          }
        : null,
      usedRunOverride: false,
    }
  }

  return { resolveRunModel }
}
