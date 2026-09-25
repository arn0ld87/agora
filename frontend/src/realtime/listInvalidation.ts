/**
 * Listen-Invalidierung über Supabase Realtime (#1618, Plan §23).
 *
 * Ein Kanal je aktivem Workspace hört auf `INSERT`/`UPDATE` der Tabellen aus
 * `REALTIME_LIST_TABLES`. Ein Ereignis ruft nur die registrierten Nachlader
 * auf; die Daten kommen weiter über die Flask-API. Das SSE laufender Läufe
 * bleibt unberührt.
 *
 * Aktiv nur mit `realtime_enabled`, Supabase-Session und aktivem Workspace.
 * Ereignisse aus einem anderen Workspace werden verworfen, auch wenn der
 * Server-Filter und RLS sie schon ausschließen sollten.
 */
import { effectScope, getCurrentScope, onScopeDispose, watch, type EffectScope } from 'vue'
import type { RealtimeChannel } from '@supabase/supabase-js'
import { getSupabaseClient } from '../auth/supabaseClient'
import {
  REALTIME_LIST_TABLES,
  RealtimeListChangeSchema,
  type RealtimeListTable,
} from '../contracts/realtimeListChangeContract'
import { useAuthStore } from '../store/auth'

type Reload = (table: RealtimeListTable) => void

/** Höchstens ein Nachladen je Tabelle und Intervall (Läufe melden Fortschritt oft). */
export const INVALIDATION_INTERVAL_MS = 1000

const listeners = new Map<RealtimeListTable, Set<Reload>>()
const pending = new Map<RealtimeListTable, ReturnType<typeof setTimeout>>()
let channel: RealtimeChannel | null = null
let channelWorkspace: string | null = null
let scope: EffectScope | null = null

function listenerCount(): number {
  let n = 0
  for (const set of listeners.values()) n += set.size
  return n
}

function flush(table: RealtimeListTable): void {
  pending.delete(table)
  for (const reload of [...(listeners.get(table) ?? [])]) {
    try {
      reload(table)
    } catch {
      // Ein Nachlader darf die anderen nicht aufhalten.
    }
  }
}

function schedule(table: RealtimeListTable): void {
  if (pending.has(table)) return
  pending.set(table, setTimeout(() => flush(table), INVALIDATION_INTERVAL_MS))
}

/** Verarbeitet ein Realtime-Ereignis; exportiert für Tests. */
export function handleChange(payload: unknown): void {
  const parsed = RealtimeListChangeSchema.safeParse(payload)
  if (!parsed.success) return
  if (!channelWorkspace || parsed.data.new.workspace_id !== channelWorkspace) return
  schedule(parsed.data.table)
}

function closeChannel(): void {
  const client = getSupabaseClient()
  if (channel && client) void client.removeChannel(channel)
  channel = null
  channelWorkspace = null
  for (const timer of pending.values()) clearTimeout(timer)
  pending.clear()
}

function openChannel(workspaceId: string | null): void {
  if (workspaceId === channelWorkspace) return
  closeChannel()
  const client = getSupabaseClient()
  if (!workspaceId || !client) return
  let next = client.channel(`agora-lists:${workspaceId}`)
  for (const table of REALTIME_LIST_TABLES) {
    for (const event of ['INSERT', 'UPDATE'] as const) {
      next = next.on(
        'postgres_changes',
        { event, schema: 'agora', table, filter: `workspace_id=eq.${workspaceId}` },
        handleChange,
      )
    }
  }
  channel = next
  channelWorkspace = workspaceId
  next.subscribe()
}

function start(): void {
  if (scope) return
  let auth: ReturnType<typeof useAuthStore>
  try {
    auth = useAuthStore()
  } catch {
    // Pinia noch nicht aktiv: kein Realtime, das Polling bleibt.
    return
  }
  scope = effectScope(true)
  scope.run(() => {
    watch(
      () =>
        auth.jwtEnabled && auth.config?.realtime_enabled === true && auth.session
          ? auth.activeWorkspaceId
          : null,
      (workspaceId) => openChannel(workspaceId),
      { immediate: true },
    )
  })
}

function stop(): void {
  scope?.stop()
  scope = null
  closeChannel()
}

/**
 * Registriert einen Nachlader für die angegebenen Tabellen. Gibt die
 * Abmeldung zurück; in einem Vue-Scope geschieht sie beim Abbau automatisch.
 */
export function onListInvalidated(tables: readonly RealtimeListTable[], reload: Reload): () => void {
  for (const table of tables) {
    if (!listeners.has(table)) listeners.set(table, new Set())
    listeners.get(table)!.add(reload)
  }
  start()
  let active = true
  const off = (): void => {
    if (!active) return
    active = false
    for (const table of tables) listeners.get(table)?.delete(reload)
    if (listenerCount() === 0) stop()
  }
  if (getCurrentScope()) onScopeDispose(off)
  return off
}

/** Nur für Tests: Zustand zurücksetzen. */
export function _resetListInvalidation(): void {
  stop()
  listeners.clear()
}
