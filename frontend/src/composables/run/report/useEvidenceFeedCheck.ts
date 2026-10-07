/**
 * Feed-Snapshot für die Prüfung der Feed-Sprünge (Etappe 5, #1804). Nutzt die
 * Datenschicht der Simulation (`useRunFeed`, Etappe 4) ohne zweiten Ladepfad und
 * ohne SSE-Strom: nur ein Snapshot-Abruf (`reload`), und erst, wenn `wanted()`
 * wahr wird (Claim gewählt und mindestens ein Beleg mit `origin_post_id`).
 *
 * state  idle     noch nicht angefordert
 *        loading  Snapshot wird geladen
 *        ready    Snapshot da, Beiträge prüfbar
 *        error    Snapshot nicht ladbar; die Belegspalte bleibt, nur ohne Feed-Sprung
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { useRunFeed } from '@/composables/run/simulation/useRunFeed'

export type EvidenceFeedState = 'idle' | 'loading' | 'ready' | 'error'

export interface EvidenceFeedCheck {
  state: ComputedRef<EvidenceFeedState>
  posts: ComputedRef<ReadonlyArray<{ post_id: string; body: string }>>
}

export function useEvidenceFeedCheck(simulationId: () => string, wanted: () => boolean): EvidenceFeedCheck {
  const id = computed(simulationId)
  const feed = useRunFeed(id as Ref<string>, { immediate: false })
  const requested = ref(false)
  const loaded = ref(false)

  watch(
    () => [wanted(), id.value] as const,
    ([want], previous) => {
      if (previous && previous[1] !== id.value) {
        requested.value = false
        loaded.value = false
      }
      if (!want || requested.value) return
      requested.value = true
      void feed.reload().finally(() => {
        loaded.value = true
      })
    },
    { immediate: true },
  )

  const state = computed<EvidenceFeedState>(() => {
    if (!requested.value) return 'idle'
    if (!loaded.value) return 'loading'
    return feed.error.value ? 'error' : 'ready'
  })
  return { state, posts: computed(() => feed.posts.value) }
}
