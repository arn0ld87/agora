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

import { AiModelSourceSchema } from './aiModelRef'
import { RouteSourceSchema } from './aiProviderContract'
import { ReasoningEffortSchema, StageIdSchema } from './llmRoute'

// === ManifestStatus ===
export const ManifestStatusSchema = z.enum(['draft', 'final', 'legacy'])
export type ManifestStatus = z.infer<typeof ManifestStatusSchema>

// === ManifestInputs ===
// seed_document_hash/seed_document_filename sind optional (Issue #1274
// Punkt 6): ist die Quelle eines Runs nicht ermittelbar, ist `null` ehrlicher
// als der frühere Platzhalter "unknown".
export const ManifestInputsSchema = z
  .object({
    seed_document_hash: z.string().nullable().optional(),
    seed_document_filename: z.string().nullable().optional(),
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

// === AiRouteSnapshot (Issue #1274 Punkt 2) ===
// Ersetzt das vorherige offene `z.record(z.string(), z.unknown())`: der
// interne `__legacy_stage_route__`-Transportkanal von AiRoute ist hier
// bereits aufgelöst, secret-tragende Provider-Optionen sind entfernt.
export const AiRouteSnapshotSchema = z
  .object({
    stage: StageIdSchema.nullable().optional(),
    provider_connection_id: z.string().nullable().optional(),
    model_id: z.string().nullable().optional(),
    source: RouteSourceSchema,
    fallback_reason: z.string().nullable().optional(),
    temperature: z.number().nullable().optional(),
    max_tokens: z.number().int().nullable().optional(),
    reasoning_effort: ReasoningEffortSchema.default('none'),
    provider_options: z.record(z.string(), z.unknown()).default(() => ({})),
  })
  .strict()
export type AiRouteSnapshot = z.infer<typeof AiRouteSnapshotSchema>

// === StageRoute ===
// base_url ist optional (Issue #1274 Punkt 4): eine aus Run-Metadaten
// rekonstruierte Legacy-Route kennt oft nur Modell und Provider.
export const StageRouteSchema = z
  .object({
    model: z.string(),
    provider: z.string(),
    base_url: z.string().nullable().optional(),
    ai_route_snapshot: AiRouteSnapshotSchema.nullable().optional(),
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
// random_seed/simulation_id_seed sind optional (Issue #1274 Punkt 1/4): Agora
// hat kein echtes RNG-Seed-Konzept — `null` ist die ehrliche Aussage "kein
// Seed vorhanden" statt eines fabrizierten Platzhalters.
export const ManifestSeedsSchema = z
  .object({
    random_seed: z.number().int().nullable().optional(),
    simulation_id_seed: z.string().nullable().optional(),
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

// === ManifestSimulationParams (Issue #1274 Punkt 3) ===
// Start-Parameter für 1:1-Replay. Optional auf RunManifest-Ebene, damit
// Manifeste vor dieser Änderung lesbar bleiben — ein fehlendes Feld dort
// bedeutet "unbekannt", nicht "Defaults galten".
export const ManifestSimulationParamsSchema = z
  .object({
    platform: z.string(),
    max_rounds: z.number().int().nullable().optional(),
    enable_graph_memory_update: z.boolean(),
    memory_update_graph_id: z.string().nullable().optional(),
  })
  .strict()
export type ManifestSimulationParams = z.infer<typeof ManifestSimulationParamsSchema>

// === ManifestDeviation (Issue #1274 Punkt 3) ===
export const ManifestDeviationSchema = z
  .object({
    field: z.string(),
    original: z.unknown().nullable().optional(),
    replay: z.unknown().nullable().optional(),
  })
  .strict()
export type ManifestDeviation = z.infer<typeof ManifestDeviationSchema>

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
    simulation: ManifestSimulationParamsSchema.nullable().optional(),
    deviations: z.array(ManifestDeviationSchema).default(() => []),
    status: ManifestStatusSchema,
  })
  .strict()
export type RunManifest = z.infer<typeof RunManifestSchema>

// === ReplayOverrides ===
// ai_model_ref spiegelt den kanonischen Backend-``AiModelRef``: beide
// Pflichtfelder erzwungen, unbekannte Schlüssel abgelehnt. ``source`` hat
// backendseitig einen Default und ist deshalb hier optional.
export const ReplayAiModelRefSchema = z
  .object({
    provider_connection_id: z.string().min(1),
    model_id: z.string().min(1),
    source: AiModelSourceSchema.optional(),
    capability_filter: z.string().nullable().optional(),
    fallback_reason: z.string().nullable().optional(),
  })
  .strict()

export const ReplayOverridesSchema = z
  .object({
    seed_document_id: z.string().nullable().optional(),
    random_seed: z.number().int().nullable().optional(),
    ai_model_ref: ReplayAiModelRefSchema.nullable().optional(),
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
