/**
 * onboardingGuard — Redirect-Guard fürs resumierbare Onboarding
 * (Onboarding Slice 2).
 *
 * Läuft NACH dem bestehenden Auth-Guard in router/index.ts. Leitet auf
 * `/onboarding` um, wenn `store.onboardingRequired` true ist und das Ziel
 * weder die Onboarding-Route noch NotFound ist. `ensureLoaded()` lädt
 * Profil + Onboarding-Status genau einmal; JEDER Fehlerpfad lässt die
 * Navigation durch — ein Backend-Ausfall darf die App niemals sperren.
 */
import type { RouteLocationNormalized, RouteLocationRaw } from 'vue-router'
import { useUserProfileStore } from '../store/userProfile'

const EXEMPT_ROUTE_NAMES = new Set(['Onboarding', 'NotFound'])

export async function onboardingGuard(
  to: RouteLocationNormalized,
): Promise<boolean | RouteLocationRaw> {
  if (to.name != null && EXEMPT_ROUTE_NAMES.has(String(to.name))) {
    return true
  }

  let store: ReturnType<typeof useUserProfileStore>
  try {
    store = useUserProfileStore()
    await store.ensureLoaded()
  } catch {
    // Kein aktives Pinia, Netzwerkfehler o.ä. — Navigation nie blockieren.
    return true
  }

  if (store.onboardingRequired) {
    return { name: 'Onboarding' }
  }
  return true
}
