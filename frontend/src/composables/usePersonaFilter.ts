/**
 * usePersonaFilter — Composable für Persona-Such- und Sichtbarkeits-Filter (Sub-Slice 40, Refs #203).
 *
 * Extrahiert aus Step2EnvSetup.vue (Zeilen 68–69 + 126–150).
 *
 * Kapselt:
 *   - Filter-State: personaSearch, showAllPersonas
 *   - Computeds: filteredPersonas (case-insensitive Volltextsuche), visiblePersonas (Slice-Logik)
 *
 * Härtungen gegenüber Original:
 *   - `interested_topics`: Array → joined; String → direkt in den Hay-Stack; sonst leer.
 *     Original `(p.interested_topics || []).join(' ')` würde bei String einen TypeError werfen.
 *   - Optional-Chaining auf alle Felder (p?.username etc.) schützt gegen null/undefined-Profile.
 */

import { ref, computed, type Ref, type ComputedRef } from 'vue'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const VISIBLE_DEFAULT_LIMIT = 24

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UsePersonaFilterDeps {
  profiles: Ref<unknown[]>
}

export interface UsePersonaFilterReturn {
  personaSearch: Ref<string>
  showAllPersonas: Ref<boolean>
  filteredPersonas: ComputedRef<unknown[]>
  visiblePersonas: ComputedRef<unknown[]>
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function usePersonaFilter(deps: UsePersonaFilterDeps): UsePersonaFilterReturn {
  const { profiles } = deps

  const personaSearch = ref('')
  const showAllPersonas = ref(false)

  const filteredPersonas: ComputedRef<unknown[]> = computed(() => {
    const q = personaSearch.value.trim().toLowerCase()
    if (!q) return profiles.value
    return profiles.value.filter((p) => {
      const profile = p as Record<string, unknown> | null | undefined

      // Resolve interested_topics to a string fragment safely.
      let topicsStr: string
      const topics = profile?.interested_topics
      if (Array.isArray(topics)) {
        topicsStr = topics.join(' ')
      } else if (typeof topics === 'string') {
        topicsStr = topics
      } else {
        topicsStr = ''
      }

      const hay = [
        profile?.username,
        profile?.name,
        profile?.bio,
        profile?.persona,
        profile?.profession,
        profile?.country,
        profile?.mbti,
        topicsStr,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()

      return hay.includes(q)
    })
  })

  const visiblePersonas: ComputedRef<unknown[]> = computed(() => {
    if (showAllPersonas.value || personaSearch.value.trim()) {
      return filteredPersonas.value
    }
    return filteredPersonas.value.slice(0, VISIBLE_DEFAULT_LIMIT)
  })

  return { personaSearch, showAllPersonas, filteredPersonas, visiblePersonas }
}
