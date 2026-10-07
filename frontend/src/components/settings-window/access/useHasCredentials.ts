import { computed, type ComputedRef } from 'vue'
import { useAuthStore } from '@/store/auth'

/**
 * Ob Token oder Sitzung vorliegt — die Bedingung, die die Routen
 * `settings/api-keys` / `audit-logs` über `requiresAuth` erzwangen. Ohne
 * aktives Pinia (isolierte Komponententests) gilt: keine Anmeldung.
 */
export function useHasCredentials(): ComputedRef<boolean> {
  let auth: ReturnType<typeof useAuthStore> | null = null
  try {
    auth = useAuthStore()
  } catch {
    auth = null
  }
  return computed(() => auth?.isAuthenticated ?? false)
}
