/**
 * useOperatorAccess — ob die aktuelle Anmeldung Betreiber-Zugang hat (#1617).
 *
 * Prozessweiter Zustand (Einstellungen, Onboarding, Logs) ist im Backend
 * `operator_only`: Supabase-Sessions bekommen dort 403. Master-Token,
 * `ago_`-Keys und der offene Modus behalten den Zugang. Ohne aktives Pinia
 * (isolierte Komponententests) bleibt es beim bisherigen Verhalten: Zugang.
 */
import { computed, type ComputedRef } from 'vue'
import { useAuthStore } from '../store/auth'

export function useOperatorAccess(): ComputedRef<boolean> {
  let auth: ReturnType<typeof useAuthStore> | null = null
  try {
    auth = useAuthStore()
  } catch {
    auth = null
  }
  return computed(() => auth?.operatorAccess ?? true)
}
