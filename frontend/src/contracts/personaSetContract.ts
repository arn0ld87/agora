/**
 * Zod-Spiegel von `backend/app/contracts/persona_set_contract.py` (#1807,
 * Etappe 7): Personasätze unter `/api/persona-sets`. Die Formen folgen den
 * generierten `schemas/persona-set-*.schema.json`; `personaSetContract.spec.ts`
 * gleicht die Feldlisten ab.
 *
 * Antwortformen (`…Schema`) tragen alle Felder, die das Backend immer
 * serialisiert. Anfrageformen (`…InputSchema`/`…RequestSchema`) lassen Felder mit
 * Vorgabewert weg, wie der Pydantic-Vertrag.
 */
import { z } from 'zod'

export const PERSONA_SET_NAME_MAX_LENGTH = 120
export const PERSONA_SET_DESCRIPTION_MAX_LENGTH = 2000
export const PERSONA_SET_MAX_ENTRIES = 500

/** Herkunft einer Persona im Satz. `fallback` ist eine sichtbare Degradation. */
export const PersonaOriginSchema = z.enum(['graph', 'manual', 'ai_draft', 'fallback'])
export type PersonaOrigin = z.infer<typeof PersonaOriginSchema>

export const PersonaGenderSchema = z.enum(['male', 'female', 'nonbinary', 'other'])
export const PersonaMbtiSchema = z.enum([
  'INTJ', 'INTP', 'ENTJ', 'ENTP', 'INFJ', 'INFP', 'ENFJ', 'ENFP',
  'ISTJ', 'ISFJ', 'ESTJ', 'ESFJ', 'ISTP', 'ISFP', 'ESTP', 'ESFP',
])
export const PersonaKindSchema = z.enum(['individual', 'collective'])

const PersonaSetNameSchema = z.string().trim().min(1).max(PERSONA_SET_NAME_MAX_LENGTH)
const PersonaSetDescriptionSchema = z.string().max(PERSONA_SET_DESCRIPTION_MAX_LENGTH)

// --- Profil -----------------------------------------------------------------

const profileInputShape = {
  username: z.string().min(1).max(64),
  name: z.string().min(1).max(120),
  bio: z.string().max(500).default(''),
  persona: z.string().max(12000).default(''),
  age: z.number().int().min(0).max(120).nullable().default(null),
  gender: PersonaGenderSchema.nullable().default(null),
  mbti: PersonaMbtiSchema.nullable().default(null),
  country: z.string().length(2).nullable().default(null),
  profession: z.string().max(200).nullable().default(null),
  interested_topics: z.array(z.string()).max(15).default([]),
  source_entity_type: z.string().max(120).nullable().default(null),
  persona_kind: PersonaKindSchema.default('individual'),
  language: z.string().max(16).nullable().default(null),
  activity_level: z.number().min(0).max(1).nullable().default(null),
  time_zone: z.string().max(64).nullable().default(null),
  location: z.string().max(200).nullable().default(null),
  verified: z.boolean().default(false),
}

/** Profil in Anfragen: nur `username` und `name` sind Pflicht. */
export const PersonaSetProfileInputSchema = z.object(profileInputShape).strict()
export type PersonaSetProfileInput = z.input<typeof PersonaSetProfileInputSchema>

/** Profil in Antworten: alle Felder sind gesetzt (Backend serialisiert Vorgaben mit). */
export const PersonaSetProfileSchema = z.object(profileInputShape).strict()
export type PersonaSetProfile = z.infer<typeof PersonaSetProfileSchema>

// --- Eintrag, Satz ----------------------------------------------------------

export const PersonaSetEntrySchema = z
  .object({
    entry_id: z.string().min(1).max(64),
    origin: PersonaOriginSchema,
    profile: PersonaSetProfileSchema,
    source_entity_uuid: z.string().max(128).nullable(),
    created_at: z.string(),
    updated_at: z.string(),
  })
  .strict()
export type PersonaSetEntry = z.infer<typeof PersonaSetEntrySchema>

/** Kachel-Sicht ohne Einträge. `locked_at` ist der maßgebliche Sperrzeitpunkt. */
export const PersonaSetSummarySchema = z
  .object({
    id: z.string(),
    name: z.string(),
    description: z.string(),
    graph_id: z.string().nullable(),
    project_id: z.string().nullable(),
    entry_count: z.number().int().min(0),
    locked: z.boolean(),
    locked_at: z.string().nullable(),
    usage_count: z.number().int().min(0),
    created_at: z.string(),
    updated_at: z.string(),
    schema_version: z.literal(1),
  })
  .strict()
export type PersonaSetSummary = z.infer<typeof PersonaSetSummarySchema>

/** Vollständiger Satz. `used_by_simulation_ids` nicht leer heißt `locked_at` gesetzt. */
export const PersonaSetRecordSchema = z
  .object({
    id: z.string().min(1).max(64),
    name: PersonaSetNameSchema,
    description: PersonaSetDescriptionSchema,
    graph_id: z.string().max(128).nullable(),
    project_id: z.string().max(128).nullable(),
    entries: z.array(PersonaSetEntrySchema).max(PERSONA_SET_MAX_ENTRIES),
    locked_at: z.string().nullable(),
    used_by_simulation_ids: z.array(z.string()),
    created_at: z.string(),
    updated_at: z.string(),
    schema_version: z.literal(1),
  })
  .strict()
  .refine((r) => r.used_by_simulation_ids.length === 0 || r.locked_at !== null, {
    message: 'a persona set used by a simulation must be locked (locked_at)',
    path: ['locked_at'],
  })
export type PersonaSetRecord = z.infer<typeof PersonaSetRecordSchema>

// --- Antworten --------------------------------------------------------------

export const PersonaSetListResponseSchema = z
  .object({
    count: z.number().int().min(0),
    sets: z.array(PersonaSetSummarySchema),
  })
  .strict()
export type PersonaSetListResponse = z.infer<typeof PersonaSetListResponseSchema>

export const PersonaSetDeleteResponseSchema = z.object({ removed: z.string() }).strict()
export type PersonaSetDeleteResponse = z.infer<typeof PersonaSetDeleteResponseSchema>

export const PersonaSetEntriesDeleteResponseSchema = z
  .object({
    removed_entry_ids: z.array(z.string()),
    set: PersonaSetSummarySchema,
  })
  .strict()
export type PersonaSetEntriesDeleteResponse = z.infer<typeof PersonaSetEntriesDeleteResponseSchema>

// --- Qualität ---------------------------------------------------------------

export const PersonaSetQualitySeveritySchema = z.enum(['error', 'warning', 'info'])

export const PersonaSetQualityIssueSchema = z
  .object({
    code: z.string(),
    severity: PersonaSetQualitySeveritySchema,
    detail: z.record(z.string(), z.unknown()).nullable().optional(),
  })
  .strict()
export type PersonaSetQualityIssue = z.infer<typeof PersonaSetQualityIssueSchema>

export const PersonaSetQualityPersonaSchema = z
  .object({
    entry_id: z.string(),
    username: z.string(),
    issues: z.array(PersonaSetQualityIssueSchema),
  })
  .strict()

export const PersonaSetQualitySummarySchema = z
  .object({
    total: z.number().int().min(0),
    role_diversity: z.number().min(0),
    mbti_diversity: z.number().min(0),
    distinct_roles: z.array(z.string()),
    distinct_mbti: z.array(z.string()),
  })
  .strict()

export const PersonaSetQualityReportSchema = z
  .object({
    set_id: z.string(),
    summary: PersonaSetQualitySummarySchema,
    global_issues: z.array(PersonaSetQualityIssueSchema),
    personas: z.array(PersonaSetQualityPersonaSchema),
  })
  .strict()
export type PersonaSetQualityReport = z.infer<typeof PersonaSetQualityReportSchema>

// --- Anfragen ---------------------------------------------------------------

export const PersonaSetCreateSchema = z
  .object({
    name: PersonaSetNameSchema,
    description: PersonaSetDescriptionSchema.default(''),
    graph_id: z.string().max(128).nullable().default(null),
    project_id: z.string().max(128).nullable().default(null),
  })
  .strict()
export type PersonaSetCreate = z.input<typeof PersonaSetCreateSchema>

export const PersonaSetUpdateSchema = z
  .object({
    name: PersonaSetNameSchema.nullable().optional(),
    description: PersonaSetDescriptionSchema.nullable().optional(),
  })
  .strict()
  .refine((v) => (v.name ?? null) !== null || (v.description ?? null) !== null, {
    message: 'at least one of name, description is required',
  })
export type PersonaSetUpdate = z.input<typeof PersonaSetUpdateSchema>

export const PersonaSetDuplicateSchema = z.object({ name: PersonaSetNameSchema }).strict()
export type PersonaSetDuplicate = z.input<typeof PersonaSetDuplicateSchema>

export const PersonaSetEntryCreateSchema = z
  .object({
    origin: PersonaOriginSchema,
    profile: PersonaSetProfileInputSchema,
    source_entity_uuid: z.string().max(128).nullable().default(null),
  })
  .strict()
export type PersonaSetEntryCreate = z.input<typeof PersonaSetEntryCreateSchema>

export const PersonaSetEntryUpdateSchema = z
  .object({
    origin: PersonaOriginSchema.nullable().optional(),
    profile: PersonaSetProfileInputSchema.nullable().optional(),
  })
  .strict()
  .refine((v) => (v.origin ?? null) !== null || (v.profile ?? null) !== null, {
    message: 'at least one of origin, profile is required',
  })
export type PersonaSetEntryUpdate = z.input<typeof PersonaSetEntryUpdateSchema>

/**
 * Anfrage `POST /api/simulation/create-from-personas`
 * (`backend/app/api/simulation_lifecycle.py`): genau eine Quelle der Personas.
 * `persona_set_id` schließt nicht-leere `template_ids`/`personas` aus; das
 * Backend antwortet sonst mit 400. Der Satz wird erst nach erfolgreichem Anlegen
 * des Laufs gesperrt.
 */
export const CreateFromPersonasRequestSchema = z
  .object({
    simulation_requirement: z.string(),
    persona_set_id: z.string().trim().min(1).optional(),
    template_ids: z.array(z.string()).optional(),
    personas: z.array(z.record(z.string(), z.unknown())).optional(),
  })
  .refine(
    (v) =>
      v.persona_set_id === undefined ||
      ((v.template_ids?.length ?? 0) === 0 && (v.personas?.length ?? 0) === 0),
    { message: 'Provide only one of persona_set_id, template_ids or personas', path: ['persona_set_id'] },
  )
export type CreateFromPersonasRequest = z.input<typeof CreateFromPersonasRequestSchema>

export const PersonaSetEntriesDeleteSchema = z
  .object({
    entry_ids: z.array(z.string()).min(1).max(PERSONA_SET_MAX_ENTRIES),
  })
  .strict()
export type PersonaSetEntriesDelete = z.input<typeof PersonaSetEntriesDeleteSchema>
