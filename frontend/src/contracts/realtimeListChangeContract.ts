/**
 * Realtime-Änderung einer Listen-Tabelle (#1618, Plan §23).
 *
 * Quelle ist kein Flask-Endpunkt, sondern Supabase Realtime (`postgres_changes`)
 * auf die Tabellen, die Alembic `dc4e84e7c000` in die Publication
 * `supabase_realtime` aufnimmt. Gelesen werden nur Tabelle, Ereignisart und
 * `workspace_id`: Ein Ereignis ist ein Signal zum Nachladen über die API, der
 * übrige Payload ist keine Datenquelle.
 */
import { z } from 'zod'

/** Tabellen in `agora`, die Realtime veröffentlicht. */
export const REALTIME_LIST_TABLES = ['projects', 'simulations', 'runs', 'reports'] as const

export const RealtimeListTableSchema = z.enum(REALTIME_LIST_TABLES)
export type RealtimeListTable = z.infer<typeof RealtimeListTableSchema>

export const RealtimeListChangeSchema = z.object({
  schema: z.literal('agora'),
  table: RealtimeListTableSchema,
  // DELETE und TRUNCATE veröffentlicht die Migration nicht: Realtime kann
  // sie nicht gegen RLS prüfen.
  eventType: z.enum(['INSERT', 'UPDATE']),
  new: z.object({ workspace_id: z.string().uuid() }),
})

export type RealtimeListChange = z.infer<typeof RealtimeListChangeSchema>
