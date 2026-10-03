/**
 * PostCreatedEvent — Zod-Spiegel für backend/app/contracts/post_event_contract.py
 *
 * v2: PostKind, like_count, parent_comment_id, parent_persona_id,
 *     parent_persona_name, quote_body, quoted_post_id, reposted_post_id,
 *     root_post_id, round_num (#1713).
 *
 * Alle neuen Felder sind nullable+optional (backward-compatible mit bestehenden
 * Consumer-Typen; bestehender Parsed-Output bleibt unverändert).
 *
 * Wording-Glossar v1: is_simulated=true ist Pflicht-Marker für alle
 * OASIS-emittierten Posts. Frontend rendert SIM-Badge. Kein "prediction".
 *
 * Nicht gespiegelt: der Backend-Validator body_required_unless_repost
 * (nicht-leerer body außer bei kind=repost). Ein .superRefine würde das
 * Objekt-Shape verdecken, das der Drift-Test prüft; der Server erzwingt ihn.
 *
 * Schema-Quelle: schemas/post-created-event.schema.json
 */

import { z } from 'zod'

export const PlatformSchema = z.enum(['reddit', 'twitter'])
export type Platform = z.infer<typeof PlatformSchema>

export const VoiceRegisterSchema = z.enum([
  'formal-de',
  'neutral-de',
  'technical-de',
  'skeptisch-de',
  'betroffen-de',
  'emotional-de',
  'umgangssprachlich-de',
])
export type VoiceRegister = z.infer<typeof VoiceRegisterSchema>

/**
 * Diskurs-Art eines Beitrags (#1713).
 * null/undefined markiert Vor-Slice-UI-2a-Daten.
 */
export const PostKindSchema = z.enum(['post', 'comment', 'quote', 'repost'])
export type PostKind = z.infer<typeof PostKindSchema>

export const PostCreatedEventSchema = z
  .object({
    event_type: z.literal('post_created').default('post_created'),
    simulation_id: z.string().min(1),
    post_id: z.string().min(1),
    parent_post_id: z.string().nullable().default(null),
    platform: PlatformSchema,
    persona_id: z.string().min(1),
    // #1216 5a — Anzeigename der Persona (keine erfundene ID-Muster mehr).
    persona_name: z.string().min(1),
    voice_register: VoiceRegisterSchema,
    is_simulated: z.boolean().default(true),
    // body: leer erlaubt bei kind=repost (kein eigener Text).
    body: z.string().default(''),
    timestamp: z.string().datetime({ offset: true }),
    // Voting-Score aus der Simulations-DB. #1209 5b: sentiment entfernt.
    score: z.number().int().default(0),
    // Sim-Zeit (tz-aware ISO-8601). null/undefined bei Pre-Task-1-Daten.
    sim_time: z.string().datetime({ offset: true }).nullable().optional(),
    // v2-Felder (#1713) — nullable+optional für Rückwärtskompatibilität ------
    /** Diskurs-Art. null/undefined bei Pre-Slice-UI-2a-Daten. */
    kind: PostKindSchema.nullable().optional(),
    /** Likes zum Emissionszeitpunkt. null/undefined bei Altdaten. */
    like_count: z.number().int().nullable().optional(),
    /** Elternkommentar im Reddit-Strang. Gesetzt wenn der nested-comments-Patch
     *  aktiv ist (camel-oasis==0.2.5, nur Reddit). Twitter kennt dieses Feld
     *  nicht (#1713 S5). */
    parent_comment_id: z.string().nullable().optional(),
    /** persona_id der Eltern-Persona (Antwort/Zitat/Repost). */
    parent_persona_id: z.string().nullable().optional(),
    /** Anzeigename der Eltern-Persona für die Kontextzeile. */
    parent_persona_name: z.string().nullable().optional(),
    /** Text des zitierten Beitrags bei kind=quote. */
    quote_body: z.string().nullable().optional(),
    /** post_id des zitierten Beitrags bei kind=quote. */
    quoted_post_id: z.string().nullable().optional(),
    /** post_id des geteilten Beitrags bei kind=repost. */
    reposted_post_id: z.string().nullable().optional(),
    /** Wurzel-Post des Strangs. */
    root_post_id: z.string().nullable().optional(),
    /** Sim-Runde. null/undefined bei Altdaten. */
    round_num: z.number().int().nullable().optional(),
  })
  .strict()

export type PostCreatedEvent = z.infer<typeof PostCreatedEventSchema>
