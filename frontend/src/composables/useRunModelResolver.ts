import type { AiModelRefPayload } from '@/api/report'
import { getRunModelOverride } from '@/store/runModelOverride'
import { useEffectiveModelSelection } from './useEffectiveModelSelection'

export interface RunModelResolution {
  ref: AiModelRefPayload | null
  usedRunOverride: boolean
}

function toPayload(
  ref: Pick<AiModelRefPayload, 'provider_connection_id' | 'model_id' | 'source'> & {
    fallback_reason?: string | null
  },
): AiModelRefPayload {
  return {
    provider_connection_id: ref.provider_connection_id,
    model_id: ref.model_id,
    source: ref.source,
    // Issue #901: nur mitsenden, wenn vorhanden. Ein leeres Feld im Request
    // waere kein Erkenntnisgewinn, ein verworfener Grund dagegen ein echter
    // Diagnoseverlust — AiModelPicker liefert unknown_provider,
    // provider_offline oder provider_degraded.
    ...(ref.fallback_reason ? { fallback_reason: ref.fallback_reason } : {}),
  }
}

export function useRunModelResolver(): {
  resolveRunModel: () => Promise<RunModelResolution>
} {
  const effectiveModel = useEffectiveModelSelection()

  async function resolveRunModel(): Promise<RunModelResolution> {
    const override = getRunModelOverride()
    if (override) {
      return { ref: toPayload(override), usedRunOverride: true }
    }

    try {
      await effectiveModel.ensureLoaded()
    } catch (err) {
      // Best effort: Ohne ladbaren Kanon entscheidet das Backend-Routing —
      // aber nicht stumm, sonst ist genau dieser Fall nicht diagnostizierbar.
      console.warn(
        '[useRunModelResolver] Kanon nicht ladbar, Backend-Routing entscheidet',
        err,
      )
    }
    const effectiveRef = effectiveModel.effectiveRef.value
    return {
      ref: effectiveRef ? toPayload(effectiveRef) : null,
      usedRunOverride: false,
    }
  }

  return { resolveRunModel }
}
