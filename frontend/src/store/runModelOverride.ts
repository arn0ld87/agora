/**
 * runModelOverride — transiente Run-Override-Senke für die Dashboard-Modellwahl.
 *
 * HeroNewRun schreibt hier beim Start die explizite Picker-Auswahl als vollen
 * {@link AiModelRef} (inkl. ``provider_connection_id``); Step3Simulation liest
 * sie beim Sim-Start vorrangig vor dem Kanon (routing/defaults.global_default)
 * und sendet sie als autoritatives ``ai_model_ref``. Damit behält ein
 * Dashboard-Pick seine Connection-Bindung (Base-URL + Secret derselben
 * ProviderConnection), ohne den persistenten Kanon zu berühren — die
 * Phase-1-Konsolidierung („eine persistente Modell-Senke") bleibt intakt.
 *
 * Bewusst sessionStorage: tab-scoped, überlebt den mehrstufigen Flow
 * (Dashboard → Graph-Build → Env-Setup → Simulation) inklusive Reload und
 * stirbt mit dem Tab. Lebensdauer: bis zum nächsten Dashboard-Start, der die
 * Senke neu schreibt oder cleart (Profile-Start / kein Pick).
 */
import { AiModelRefSchema, type AiModelRef } from '@/contracts/aiModelRef'

export const RUN_MODEL_OVERRIDE_KEY = 'agora.run.aiModelRefOverride'

function storageOrNull(): Storage | null {
  try {
    if (typeof window === 'undefined') return null
    const ss = window.sessionStorage
    if (!ss || typeof ss.getItem !== 'function') return null
    return ss
  } catch {
    return null
  }
}

export function setRunModelOverride(ref: AiModelRef): void {
  const ss = storageOrNull()
  if (!ss) return
  // source wird auf 'run-override' normalisiert — die Senke IST die
  // Run-Override-Ebene der Auswahl-Hierarchie (Master-Prompt §6.3).
  const candidate: AiModelRef = {
    provider_connection_id: ref.provider_connection_id,
    model_id: ref.model_id,
    source: 'run-override',
  }
  if (!AiModelRefSchema.safeParse(candidate).success) return
  try {
    ss.setItem(RUN_MODEL_OVERRIDE_KEY, JSON.stringify(candidate))
  } catch {
    /* Quota/Private-Mode: Override entfällt, Kanon greift */
  }
}

export function clearRunModelOverride(): void {
  const ss = storageOrNull()
  if (!ss) return
  try {
    ss.removeItem(RUN_MODEL_OVERRIDE_KEY)
  } catch {
    /* swallow */
  }
}

export function getRunModelOverride(): AiModelRef | null {
  const ss = storageOrNull()
  if (!ss) return null
  try {
    const raw = ss.getItem(RUN_MODEL_OVERRIDE_KEY)
    if (!raw) return null
    const parsed = AiModelRefSchema.safeParse(JSON.parse(raw))
    if (!parsed.success) {
      ss.removeItem(RUN_MODEL_OVERRIDE_KEY)
      return null
    }
    return parsed.data
  } catch {
    try {
      ss.removeItem(RUN_MODEL_OVERRIDE_KEY)
    } catch {
      /* swallow */
    }
    return null
  }
}
