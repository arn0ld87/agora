/**
 * PostCreatedEvent — Zod-Spiegel für backend/app/contracts/post_event_contract.py
 *
 * Slice FE-Redesign-5-pre · 2026-05-15
 *
 * Wording-Glossar v1: is_simulated=true ist Pflicht-Marker für alle
 * OASIS-emittierten Posts. Frontend rendert SIM-Badge. Kein "prediction".
 *
 * Schema-Quelle: schemas/post-created-event.schema.json
 */

import { z } from 'zod'

export const PlatformSchema = z.enum(['reddit', 'twitter'])
export type Platform = z.infer<typeof PlatformSchema>

export const VoiceRegisterSchema = z.enum(['formal', 'casual', 'jugendsprache'])
export type VoiceRegister = z.infer<typeof VoiceRegisterSchema>

export const PostCreatedEventSchema = z
  .object({
    event_type: z.literal('post_created'),
    simulation_id: z.string().min(1),
    post_id: z.string().min(1),
    parent_post_id: z.string().nullable(),
    platform: PlatformSchema,
    persona_id: z.string().min(1),
    voice_register: VoiceRegisterSchema,
    is_simulated: z.boolean().default(true),
    body: z.string().min(1),
    timestamp: z.string().datetime({ offset: true }),
    // Phase B — Sentiment-Heatbar + Voting-Score
    sentiment: z.number().min(-1).max(1).nullable().optional(),
    score: z.number().int().default(0),
  })
  .strict()

export type PostCreatedEvent = z.infer<typeof PostCreatedEventSchema>
