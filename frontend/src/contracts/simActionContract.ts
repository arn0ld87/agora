/**
 * SimAction-Verträge — Zod-Spiegel für
 *   backend/app/contracts/sim_action_contract.py
 *
 * Schemas-Quellen:
 *   schemas/sim-action-record.schema.json
 *   schemas/sim-action-page.schema.json
 *   schemas/round-summary.schema.json
 *
 * #1713
 */

import { z } from 'zod'
import { PlatformSchema } from './postEventContract'

export { PlatformSchema }

/**
 * Bekannte Aktionsarten aus dem OASIS-Trace.
 * OTHER fängt unbekannte Werte aus Altläufen ab.
 */
export const SimActionTypeSchema = z.enum([
  'CREATE_POST',
  'CREATE_COMMENT',
  'LIKE_POST',
  'DISLIKE_POST',
  'LIKE_COMMENT',
  'DISLIKE_COMMENT',
  'REPOST',
  'QUOTE_POST',
  'FOLLOW',
  'MUTE',
  'SEARCH_POSTS',
  'SEARCH_USER',
  'TREND',
  'REFRESH',
  'DO_NOTHING',
  'INTERVIEW',
  'OTHER',
])
export type SimActionType = z.infer<typeof SimActionTypeSchema>

/** Typ-konfliktkennzeichen für Role-Leakage-Detection. */
export const RoleConflictSchema = z.enum([
  'foreign_role',
  'foreign_name_signature',
  'unmatched_self_reference',
])
export type RoleConflict = z.infer<typeof RoleConflictSchema>

/**
 * Eine einzelne protokollierte Simulationsaktion (API-Grenze).
 * Quelle: schemas/sim-action-record.schema.json
 */
export const SimActionRecordSchema = z
  .object({
    round_num: z.number().int().min(0),
    timestamp: z.string().datetime({ offset: true }),
    platform: PlatformSchema,
    agent_id: z.string().min(1),
    agent_name: z.string().min(1),
    action_type: SimActionTypeSchema,
    content: z.string().nullable().default(null),
    success: z.boolean().default(true),
    sim_time: z.string().datetime({ offset: true }).nullable().default(null),
    role_conflict: RoleConflictSchema.nullable().default(null),
    target_post_id: z.string().nullable().default(null),
    target_comment_id: z.string().nullable().default(null),
    target_agent_id: z.string().nullable().default(null),
    target_agent_name: z.string().nullable().default(null),
  })
  .strict()

export type SimActionRecord = z.infer<typeof SimActionRecordSchema>

/**
 * Cursor-paginierte Antwort für GET /api/simulation/<id>/actions.
 * Quelle: schemas/sim-action-page.schema.json
 */
export const SimActionPageSchema = z
  .object({
    items: z.array(SimActionRecordSchema),
    next_cursor: z.string().nullable().default(null),
  })
  .strict()

export type SimActionPage = z.infer<typeof SimActionPageSchema>

/**
 * Aggregierte Aktionsbilanz einer Sim-Runde je Plattform.
 * action_counts: offenes Mapping Enum-Wert → Anzahl.
 * Quelle: schemas/round-summary.schema.json
 */
export const RoundSummarySchema = z
  .object({
    round_num: z.number().int().min(0),
    platform: PlatformSchema,
    // Enum-Keys als string akzeptieren; Backend validiert die Werte serverseitig.
    action_counts: z.record(z.string(), z.number().int()).default({}),
  })
  .strict()

export type RoundSummary = z.infer<typeof RoundSummarySchema>

/**
 * Antwort für GET /api/simulation/<id>/rounds.
 */
export const RoundsResponseSchema = z
  .object({
    rounds: z.array(RoundSummarySchema),
  })
  .strict()

export type RoundsResponse = z.infer<typeof RoundsResponseSchema>
