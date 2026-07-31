/**
 * Run-Budget-Contract v1 — Zod-Spiegel (Issue #764).
 *
 * Hand-gepflegt, 1:1 zu:
 *   schemas/run-budget-config.schema.json
 *   schemas/run-usage.schema.json
 *   schemas/run-budget-status.schema.json
 *   schemas/run-preflight-estimate.schema.json
 *
 * Änderungen am Pydantic-Modell (backend/app/contracts/run_budget_contract.py)
 * → Schema-Dump → diese Datei synchronisieren.
 *
 * Regeln (gespiegelt aus dem Backend-Contract):
 *   - Geldbeträge ausschließlich als Integer-Micros (1 Einheit = 10^-6 Währung).
 *   - Unbekannte Werte sind null + Status ("unknown"/"estimated"/"free"),
 *     niemals 0 für "nicht gemessen".
 */
import { z } from "zod";

// === Literale (1:1 zum Pydantic-Contract) ===
export const BudgetDimensionSchema = z.enum(["tokens", "cost", "time", "calls"]);
export type BudgetDimension = z.infer<typeof BudgetDimensionSchema>;

export const BudgetEnforcementSchema = z.enum(["soft", "hard"]);
export type BudgetEnforcement = z.infer<typeof BudgetEnforcementSchema>;

export const CostStatusSchema = z.enum([
  "measured",
  "estimated",
  "free",
  "unknown",
]);
export type CostStatus = z.infer<typeof CostStatusSchema>;

export const TokensStatusSchema = z.enum(["measured", "partial", "unknown"]);
export type TokensStatus = z.infer<typeof TokensStatusSchema>;

export const MeasurementStatusSchema = z.enum([
  "complete",
  "partial",
  "unknown",
]);
export type MeasurementStatus = z.infer<typeof MeasurementStatusSchema>;

export const DataQualitySchema = z.enum(["high", "medium", "low", "unknown"]);
export type DataQuality = z.infer<typeof DataQualitySchema>;

export const BudgetStateSchema = z.enum(["ok", "warning", "exceeded"]);
export type BudgetState = z.infer<typeof BudgetStateSchema>;

export const TerminationReasonSchema = z.enum([
  "completed",
  "error",
  "user_cancel",
  "user_stop",
  "budget_tokens",
  "budget_cost",
  "budget_time",
  "budget_calls",
]);
export type TerminationReason = z.infer<typeof TerminationReasonSchema>;

// === RunBudgetConfig (schemas/run-budget-config.schema.json) ===
export const RunBudgetConfigSchema = z
  .object({
    schema_version: z.literal(1).default(1),
    max_tokens: z.number().int().min(1).nullable().optional(),
    max_cost_micros: z.number().int().min(1).nullable().optional(),
    max_duration_seconds: z.number().int().min(1).nullable().optional(),
    max_llm_calls: z.number().int().min(1).nullable().optional(),
    enforcement: BudgetEnforcementSchema.default("soft"),
    currency: z.string().length(3).default("USD"),
  })
  .strict();
export type RunBudgetConfig = z.infer<typeof RunBudgetConfigSchema>;

// === BudgetWarning ===
export const BudgetWarningSchema = z
  .object({
    dimension: BudgetDimensionSchema,
    severity: BudgetEnforcementSchema,
    threshold: z.number().int().min(0),
    observed: z.number().int().min(0),
    message: z.string().min(1),
    ts: z.string().min(1),
  })
  .strict();
export type BudgetWarning = z.infer<typeof BudgetWarningSchema>;

// === UsageMetrics ===
export const UsageMetricsSchema = z
  .object({
    input_tokens: z.number().int().min(0).nullable().optional(),
    output_tokens: z.number().int().min(0).nullable().optional(),
    total_tokens: z.number().int().min(0).nullable().optional(),
    llm_calls: z.number().int().min(0).default(0),
    cost_micros: z.number().int().min(0).nullable().optional(),
    cost_status: CostStatusSchema.default("unknown"),
    tokens_status: TokensStatusSchema.default("unknown"),
    duration_ms: z.number().int().min(0).default(0),
  })
  .strict();
export type UsageMetrics = z.infer<typeof UsageMetricsSchema>;

// === RunUsage (schemas/run-usage.schema.json) ===
export const RunUsageSchema = z
  .object({
    schema_version: z.literal(1).default(1),
    totals: UsageMetricsSchema,
    by_stage: z.record(z.string(), UsageMetricsSchema).default(() => ({})),
    by_provider: z.record(z.string(), UsageMetricsSchema).default(() => ({})),
    by_model: z.record(z.string(), UsageMetricsSchema).default(() => ({})),
    started_at: z.string().nullable().optional(),
    ended_at: z.string().nullable().optional(),
    measurement_status: MeasurementStatusSchema.default("unknown"),
    pricing_version: z.string().nullable().optional(),
    pricing_source: z.string().nullable().optional(),
  })
  .strict();
export type RunUsage = z.infer<typeof RunUsageSchema>;

// === RunBudgetStatus (schemas/run-budget-status.schema.json) ===
export const RunBudgetStatusSchema = z
  .object({
    config: RunBudgetConfigSchema,
    consumed: UsageMetricsSchema,
    warnings: z.array(BudgetWarningSchema).default(() => []),
    status: BudgetStateSchema.default("ok"),
    exceeded_dimension: BudgetDimensionSchema.nullable().optional(),
  })
  .strict();
export type RunBudgetStatus = z.infer<typeof RunBudgetStatusSchema>;

// === PreflightModelRef ===
export const PreflightModelRefSchema = z
  .object({
    stage: z.string().min(1),
    provider_id: z.string().min(1),
    model_id: z.string().min(1),
    base_url_sanitized: z.string().nullable().optional(),
    cost_status: CostStatusSchema.default("unknown"),
  })
  .strict();
export type PreflightModelRef = z.infer<typeof PreflightModelRefSchema>;

// === PreflightEstimate (schemas/run-preflight-estimate.schema.json) ===
export const PreflightEstimateSchema = z
  .object({
    schema_version: z.literal(1).default(1),
    is_estimate: z.literal(true),
    estimated_tokens_low: z.number().int().min(0).nullable().optional(),
    estimated_tokens_high: z.number().int().min(0).nullable().optional(),
    estimated_cost_micros_low: z.number().int().min(0).nullable().optional(),
    estimated_cost_micros_high: z.number().int().min(0).nullable().optional(),
    estimated_duration_seconds_low: z
      .number()
      .int()
      .min(0)
      .nullable()
      .optional(),
    estimated_duration_seconds_high: z
      .number()
      .int()
      .min(0)
      .nullable()
      .optional(),
    cost_status: CostStatusSchema.default("unknown"),
    models: z.array(PreflightModelRefSchema).default(() => []),
    pricing_version: z.string().min(1),
    pricing_source: z.string().min(1),
    data_quality: DataQualitySchema.default("unknown"),
    warnings: z.array(z.string()).default(() => []),
  })
  .strict();
export type PreflightEstimate = z.infer<typeof PreflightEstimateSchema>;
