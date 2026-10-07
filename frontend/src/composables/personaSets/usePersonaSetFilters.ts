/**
 * Filter und Suche über die Einträge eines Personasatzes (#1807, Etappe 7).
 * Die Auswahllisten werden aus den vorhandenen Werten der Einträge abgeleitet:
 * Herkunft (`origin`), Art (`persona_kind`) und Rolle (`profile.profession`).
 * Das Profil trägt kein Haltungsfeld, deshalb gibt es keinen Haltungsfilter.
 */
import { computed, ref, type MaybeRefOrGetter, toValue } from 'vue'
import type { PersonaOrigin, PersonaSetEntry } from '@/contracts/personaSetContract'

export const ALL = '__all__'

export function usePersonaSetFilters(entries: MaybeRefOrGetter<readonly PersonaSetEntry[]>) {
  const origin = ref<string>(ALL)
  const kind = ref<string>(ALL)
  const role = ref<string>(ALL)
  const query = ref('')

  const originOptions = computed<PersonaOrigin[]>(() => {
    const seen = new Set<PersonaOrigin>()
    for (const e of toValue(entries)) seen.add(e.origin)
    return [...seen]
  })
  const kindOptions = computed<string[]>(() => [...new Set(toValue(entries).map((e) => e.profile.persona_kind))])
  const roleOptions = computed<string[]>(() => {
    const roles = toValue(entries)
      .map((e) => e.profile.profession)
      .filter((p): p is string => typeof p === 'string' && p.trim() !== '')
    return [...new Set(roles)].sort((a, b) => a.localeCompare(b))
  })

  const isFiltered = computed(
    () => origin.value !== ALL || kind.value !== ALL || role.value !== ALL || query.value.trim() !== '',
  )

  const filtered = computed<PersonaSetEntry[]>(() => {
    const q = query.value.trim().toLowerCase()
    return toValue(entries).filter((e) => {
      if (origin.value !== ALL && e.origin !== origin.value) return false
      if (kind.value !== ALL && e.profile.persona_kind !== kind.value) return false
      if (role.value !== ALL && e.profile.profession !== role.value) return false
      if (q === '') return true
      const p = e.profile
      return [p.name, p.username, p.profession ?? '', p.bio].some((v) => v.toLowerCase().includes(q))
    })
  })

  function reset(): void {
    origin.value = ALL
    kind.value = ALL
    role.value = ALL
    query.value = ''
  }

  return { origin, kind, role, query, originOptions, kindOptions, roleOptions, isFiltered, filtered, reset }
}
