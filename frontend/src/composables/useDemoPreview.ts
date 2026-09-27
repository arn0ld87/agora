/**
 * useDemoPreview — ob der aktuelle Besuch eine Demo-Vorschau ist (#1697).
 *
 * Nur auf der oeffentlichen Demo-Instanz (Backend meldet `demo_mode: true`)
 * sehen JWT-Besucher ohne Betreiber-Zugang eine nicht-editierbare Vorschau
 * statt eines Redirects. Ohne aktives Pinia (isolierte Komponententests)
 * bleibt es beim sicheren Default: keine Vorschau.
 */
import { computed, type ComputedRef } from 'vue'
import { useAuthStore } from '../store/auth'

export function useDemoPreview(): ComputedRef<boolean> {
  let auth: ReturnType<typeof useAuthStore> | null = null
  try {
    auth = useAuthStore()
  } catch {
    auth = null
  }
  return computed(() => auth?.demoPreview ?? false)
}
