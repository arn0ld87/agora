/**
 * Runs-Contract v1 — Zod-Spiegel.
 *
 * Hand-gepflegt, 1:1 zu schemas/run-detail.schema.json und
 * schemas/runs-list-response.schema.json.
 *
 * Kanonische Status-Werte spiegeln RunRegistry.canonical_status():
 *   pending | processing | paused | completed | failed | stopped
 *
 * Änderungen am Pydantic-Modell (backend/app/contracts/runs_contract.py)
 * → Schema-Dump → diese Datei synchronisieren.
 */
import { z } from "zod";

// === RunStatus ===
export const RunStatusSchema = z.enum([
  "pending",
  "processing",
  "paused",
  "completed",
  "failed",
  "stopped",
]);
export type RunStatus = z.infer<typeof RunStatusSchema>;

// === RunSummary (Lesepfad-Anreicherung) ===
export const RunSummaryContractSchema = z
  .object({
    model: z.string().nullable().optional(),
    document_name: z.string().nullable().optional(),
    persona_count: z.number().int().nullable().optional(),
    graph_id: z.string().nullable().optional(),
    graph_name: z.string().nullable().optional(),
    branch_name: z.string().nullable().optional(),
  })
  .strict();
export type RunSummaryContract = z.infer<typeof RunSummaryContractSchema>;

// === RunDetail (vollständige Run-Repräsentation) ===
export const RunDetailSchema = z
  .object({
    run_id: z.string(),
    run_type: z.string(),
    entity_id: z.string(),
    parent_run_id: z.string().nullable().optional(),
    status: RunStatusSchema,
    progress: z.number().int().min(0).max(100),
    message: z.string().default(""),
    error: z.string().nullable().optional(),
    started_at: z.string(),
    updated_at: z.string(),
    completed_at: z.string().nullable().optional(),
    branch_label: z.string().nullable().optional(),
    metadata: z.record(z.string(), z.unknown()).default(() => ({})),
    linked_ids: z.record(z.string(), z.unknown()).default(() => ({})),
    artifacts: z.record(z.string(), z.unknown()).default(() => ({})),
    resume_capability: z.record(z.string(), z.unknown()).default(() => ({})),
    // Read-path enrichment
    summary: RunSummaryContractSchema.nullable().optional(),
    // Live-Metriken (Sub-Slice 33)
    eta_seconds: z.number().int().nullable().optional(),
    log_tail: z.array(z.string()).nullable().optional(),
    metrics: z
      .record(z.string(), z.union([z.number(), z.string()]))
      .nullable()
      .optional(),
  })
  // extra="allow" im Pydantic-Modell → kein .strict() hier
  .passthrough();
export type RunDetail = z.infer<typeof RunDetailSchema>;

// === RunsAggregation ===
export const RunsAggregationSchema = z
  .object({
    counts: z.record(z.string(), z.number().int()),
    total: z.number().int(),
  })
  .strict();
export type RunsAggregation = z.infer<typeof RunsAggregationSchema>;

// === RunsListResponse ===
export const RunsListResponseSchema = z
  .object({
    runs: z.array(RunDetailSchema),
    total: z.number().int(),
    aggregation: RunsAggregationSchema.nullable().optional(),
  })
  .strict();
export type RunsListResponse = z.infer<typeof RunsListResponseSchema>;
