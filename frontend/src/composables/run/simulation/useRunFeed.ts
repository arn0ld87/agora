/**
 * Feed-Datenschicht für „Lauf → Simulation → Feed" (Etappe 4, #1801).
 *
 * Eigenständig neben `useSimFeed` (dessen Altansichten unverändert bleiben):
 * - lädt je Netzwerk den Snapshot mit hohem `limit` (das Backend behält die
 *   NEUESTEN `limit` Einträge, Default 200, keine Klemmung),
 * - hängt sich an den SSE-Strom (`post_created`) und dedupliziert über `post_id`,
 * - hält einen Puffer mit benannter Obergrenze statt der 500 von `useSimFeed`,
 * - sammelt im Rückblick-Modus (`roundCursor` gesetzt) Live-Beiträge, statt die
 *   Liste springen zu lassen („Neue Beiträge"-Pille).
 *
 * Fehler werden nicht verschluckt: `error` trägt die Meldung, verworfene
 * vertragswidrige Einträge stehen in `invalidCount`.
 */
import {
  computed,
  getCurrentScope,
  onScopeDispose,
  readonly,
  ref,
  shallowRef,
  toValue,
  watch,
  type ComputedRef,
  type Ref,
} from 'vue'
import { getSimulationFeedSnapshotPage, type SimulationPlatform } from '@/api/simulation'
import { useEventStream } from '@/composables/useEventStream'
import type { PostCreatedEvent } from '@/contracts/postEventContract'
import { maxRoundOf, postsUpToRound } from './threads'

/** `limit` je Netzwerk beim Snapshot-Abruf (Backend klemmt nicht; 0 hieße unbegrenzt). */
export const FEED_SNAPSHOT_LIMIT = 5000

/** Obergrenze des Puffers über beide Netzwerke; darüber fallen die ältesten Beiträge heraus. */
export const RUN_FEED_MAX_POSTS = 20000

const NETWORKS: readonly SimulationPlatform[] = ['twitter', 'reddit']

export type RunFeedStreamState = 'idle' | 'connecting' | 'live' | 'error'

export interface UseRunFeedOptions {
  /** Beim Anlegen sofort Strom und Snapshot starten (Standard: ja). */
  immediate?: boolean
}

export interface UseRunFeedReturn {
  /** Alle gepufferten Beiträge, chronologisch aufsteigend. */
  posts: Readonly<Ref<readonly PostCreatedEvent[]>>
  /** `posts` bis zum `roundCursor` (alles, solange er `null` ist). */
  visiblePosts: ComputedRef<PostCreatedEvent[]>
  loading: Readonly<Ref<boolean>>
  /** Sichtbare Fehlermeldung des letzten Abrufs, sonst `null`. */
  error: Readonly<Ref<string | null>>
  /** Ein Snapshot lieferte genau `limit` Einträge: ältere Beiträge fehlen wahrscheinlich. */
  truncated: Readonly<Ref<boolean>>
  /** Vom Backend gelieferte, aber vertragswidrige und verworfene Einträge. */
  invalidCount: Readonly<Ref<number>>
  /** Beiträge, die wegen der Pufferobergrenze verdrängt wurden. */
  evictedCount: Readonly<Ref<number>>
  streamState: ComputedRef<RunFeedStreamState>
  /** Im Rückblick gesammelte Live-Beiträge. */
  pendingCount: ComputedRef<number>
  /** Übernimmt gesammelte Beiträge in `posts`. */
  flushPending: () => void
  /** `null` = live mitlaufen, Zahl = bis zu dieser Runde. */
  roundCursor: Readonly<Ref<number | null>>
  /** Setzt den Rundenregler; `null` kehrt zu live zurück und übernimmt Gesammeltes. */
  setRoundCursor: (round: number | null) => void
  /** Höchste bisher gesehene `round_num` (nur gepufferte Beiträge), sonst `null`. */
  maxRoundSeen: Readonly<Ref<number | null>>
  /** Snapshot erneut abrufen (Strom bleibt) und fehlende Beiträge ergänzen; Bekanntes bleibt unberührt. */
  reload: () => Promise<void>
  /** Strom und Snapshot starten (bei `immediate: false`). */
  start: () => Promise<void>
  /** Strom schließen. */
  stop: () => void
}

function byTime(a: PostCreatedEvent, b: PostCreatedEvent): number {
  const ta = Date.parse(a.timestamp)
  const tb = Date.parse(b.timestamp)
  return (Number.isNaN(ta) ? 0 : ta) - (Number.isNaN(tb) ? 0 : tb)
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

/**
 * Feed eines Laufs. `simulationId` darf ein Ref sein; ein Wechsel schließt den
 * Strom, leert alles und lädt neu. Räumt beim Verlassen des Effekt-Scopes auf.
 */
export function useRunFeed(
  simulationId: Ref<string> | string,
  options: UseRunFeedOptions = {},
): UseRunFeedReturn {
  const all = shallowRef<PostCreatedEvent[]>([])
  const seen = new Set<string>()
  const pending = shallowRef<PostCreatedEvent[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const truncated = ref(false)
  const invalidCount = ref(0)
  const evictedCount = ref(0)
  const roundCursor = ref<number | null>(null)
  const maxRoundSeen = ref<number | null>(null)
  const started = ref(false)
  let loadToken = 0

  const currentId = (): string => toValue(simulationId)

  function noteRounds(batch: readonly PostCreatedEvent[]): void {
    const max = maxRoundOf(batch)
    if (max !== null && (maxRoundSeen.value === null || max > maxRoundSeen.value)) {
      maxRoundSeen.value = max
    }
  }

  /** Hängt Beiträge an den Puffer; `sort` ordnet nach Zeit (Snapshot-Mischung). */
  function append(batch: PostCreatedEvent[], sort: boolean): void {
    if (batch.length === 0) return
    let next = all.value.concat(batch)
    if (sort) next = next.sort(byTime)
    const overflow = next.length - RUN_FEED_MAX_POSTS
    if (overflow > 0) {
      const dropped = next.splice(0, overflow)
      for (const p of dropped) seen.delete(p.post_id)
      evictedCount.value += dropped.length
    }
    all.value = next
    noteRounds(batch)
  }

  function ingest(post: PostCreatedEvent): void {
    if (post.simulation_id !== currentId()) return
    if (seen.has(post.post_id)) return
    seen.add(post.post_id)
    if (roundCursor.value !== null) {
      pending.value = [...pending.value, post]
      return
    }
    append([post], false)
  }

  function flushPending(): void {
    if (pending.value.length === 0) return
    const batch = pending.value
    pending.value = []
    append(batch, true)
  }

  function setRoundCursor(round: number | null): void {
    roundCursor.value = round
    if (round === null) flushPending()
  }

  const stream = useEventStream(() => currentId(), {
    post_created: ingest,
  })

  const streamState = computed<RunFeedStreamState>(() => {
    if (!started.value) return 'idle'
    if (stream.isStreaming.value) return 'live'
    if (stream.error.value) return 'error'
    return 'connecting'
  })

  async function loadSnapshot(): Promise<void> {
    const id = currentId()
    if (!id) return
    const token = ++loadToken
    loading.value = true
    error.value = null
    const results = await Promise.allSettled(
      NETWORKS.map((network) =>
        getSimulationFeedSnapshotPage(id, network, { limit: FEED_SNAPSHOT_LIMIT }),
      ),
    )
    if (token !== loadToken) return

    const fresh: PostCreatedEvent[] = []
    const messages: string[] = []
    let anyTruncated = false
    let invalid = 0
    results.forEach((result, i) => {
      if (result.status === 'rejected') {
        messages.push(`${NETWORKS[i]}: ${errorMessage(result.reason)}`)
        return
      }
      const page = result.value
      if (page.receivedCount >= FEED_SNAPSHOT_LIMIT) anyTruncated = true
      invalid += page.invalidCount
      for (const post of page.posts) {
        if (post.simulation_id !== id || seen.has(post.post_id)) continue
        seen.add(post.post_id)
        fresh.push(post)
      }
    })
    append(fresh, true)
    truncated.value = anyTruncated
    invalidCount.value = invalid
    error.value = messages.length > 0 ? messages.join('; ') : null
    loading.value = false
  }

  function resetState(): void {
    loadToken += 1
    all.value = []
    pending.value = []
    seen.clear()
    truncated.value = false
    invalidCount.value = 0
    evictedCount.value = 0
    maxRoundSeen.value = null
    roundCursor.value = null
    error.value = null
    loading.value = false
  }

  async function start(): Promise<void> {
    if (!currentId()) return
    started.value = true
    // Strom zuerst, damit zwischen Snapshot und Verbindung nichts durchfällt;
    // Überschneidungen fängt die Deduplizierung.
    await stream.start()
    await loadSnapshot()
  }

  function stop(): void {
    loadToken += 1
    loading.value = false
    stream.stop()
    started.value = false
  }

  async function reload(): Promise<void> {
    await loadSnapshot()
  }

  watch(
    () => currentId(),
    (_next, previous) => {
      if (previous === undefined) return
      stop()
      resetState()
      if (options.immediate !== false) void start()
    },
  )

  if (getCurrentScope()) onScopeDispose(stop)
  if (options.immediate !== false) void start()

  return {
    posts: readonly(all) as Readonly<Ref<readonly PostCreatedEvent[]>>,
    visiblePosts: computed(() => postsUpToRound(all.value, roundCursor.value)),
    loading: readonly(loading),
    error: readonly(error),
    truncated: readonly(truncated),
    invalidCount: readonly(invalidCount),
    evictedCount: readonly(evictedCount),
    streamState,
    pendingCount: computed(() => pending.value.length),
    flushPending,
    roundCursor: readonly(roundCursor),
    setRoundCursor,
    maxRoundSeen: readonly(maxRoundSeen),
    reload,
    start,
    stop,
  }
}
