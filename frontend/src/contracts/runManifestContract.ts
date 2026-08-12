/**
 * Run-Manifest-Contract v1 — Zod-Spiegel (Issue #763).
 *
 * Hand-gepflegt, 1:1 zu backend/app/contracts/run_manifest_contract.py und
 * den generierten JSON-Schemas unter schemas/run-manifest.schema.json etc.
 *
 * Regeln:
 *   - Keine Secrets im Manifest (API-Keys, Passwörter).
 *   - Prompt-Texte sind byte-genaue Snapshots zum Zeitpunkt des Runs.
 *   - Draft-Manifest bei Run-Start, final bei Run-Ende, legacy für Alt-Runs.
 *
 * Änderungen am Pydantic-Modell → Schema-Dump → diese Datei synchronisieren.
 */
import { z } from 'zod'

// === ManifestStatus ===
export const ManifestStatusSchema = z.enum(['draft', 'final', 'legacy'])
export type ManifestStatus = z.infer<typeof ManifestStatusSchema>

// === ManifestInputs ===
export const ManifestInputsSchema = z
  .object({
    seed_document_hash: z.string(),
    seed_document_filename: z.string(),
    simulation_config_hash: z.string(),
    graph_id: z.string(),
    graph_version: z.string().nullable().optional(),
    embedding_version: z.string().nullable().optional(),
  })
  .strict()
export type ManifestInputs = z.infer<typeof ManifestInputsSchema>

// === ManifestVersions ===
export const ManifestVersionsSchema = z
  .object({
    agora_version: z.string(),
    schema_version: z.string(),
  })
  .strict()
export type ManifestVersions = z.infer<typeof ManifestVersionsSchema>

// === StageRoute ===
export const StageRouteSchema = z
  .object({
    model: z.string(),
    provider: z.string(),
    base_url: z.string(),
    ai_route_snapshot: z.record(z.string(), z.unknown()).nullable().optional(),
  })
  .strict()
export type StageRoute = z.infer<typeof StageRouteSchema>

// === ManifestRouting ===
export const ManifestRoutingSchema = z
  .object({
    stages: z.record(z.string(), StageRouteSchema).default(() => ({})),
  })
  .strict()
export type ManifestRouting = z.infer<typeof ManifestRoutingSchema>

// === PromptSnapshot ===
export const PromptSnapshotSchema = z
  .object({
    content: z.string(),
    source_file: z.string(),
  })
  .strict()
export type PromptSnapshot = z.infer<typeof PromptSnapshotSchema>

// === ManifestPrompts ===
export const ManifestPromptsSchema = z
  .object({
    entries: z.record(z.string(), PromptSnapshotSchema).default(() => ({})),
  })
  .strict()
export type ManifestPrompts = z.infer<typeof ManifestPromptsSchema>

// === ManifestSeeds ===
export const ManifestSeedsSchema = z
  .object({
    random_seed: z.number().int(),
    simulation_id_seed: z.string(),
  })
  .strict()
export type ManifestSeeds = z.infer<typeof ManifestSeedsSchema>

// === ManifestRuntime ===
export const ManifestRuntimeSchema = z
  .object({
    started_at: z.string(),
    completed_at: z.string().nullable().optional(),
    duration_seconds: z.number().int().nullable().optional(),
    rounds_completed: z.number().int().nullable().optional(),
    usage_summary: z.record(z.string(), z.unknown()).nullable().optional(),
    termination_reason: z.string().nullable().optional(),
  })
  .strict()
export type ManifestRuntime = z.infer<typeof ManifestRuntimeSchema>

// === RunManifest ===
export const RunManifestSchema = z
  .object({
    schema_version: z.literal(1),
    run_id: z.string(),
    replayed_from_run_id: z.string().nullable().optional(),
    captured_at: z.string(),
    inputs: ManifestInputsSchema,
    versions: ManifestVersionsSchema,
    routing: ManifestRoutingSchema,
    prompts: ManifestPromptsSchema,
    seeds: ManifestSeedsSchema,
    runtime: ManifestRuntimeSchema.nullable().optional(),
    status: ManifestStatusSchema,
  })
  .strict()
export type RunManifest = z.infer<typeof RunManifestSchema>

// === ReplayOverrides ===
export const ReplayOverridesSchema = z
  .object({
    seed_document_id: z.string().nullable().optional(),
    random_seed: z.number().int().nullable().optional(),
    ai_model_ref: z.record(z.string(), z.string()).nullable().optional(),
  })
  .strict()
export type ReplayOverrides = z.infer<typeof ReplayOverridesSchema>

// === ReplayRequest ===
export const ReplayRequestSchema = z
  .object({
    overrides: ReplayOverridesSchema.nullable().optional(),
  })
  .strict()
export type ReplayRequest = z.infer<typeof ReplayRequestSchema>

// === ReplayResponse ===
export const ReplayResponseSchema = z
  .object({
    run_id: z.string(),
    status: z.string(),
  })
  .strict()
export type ReplayResponse = z.infer<typeof ReplayResponseSchema>
