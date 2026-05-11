/**
 * LLM Routing Contracts — Zod-Spiegel.
 * Spiegelt backend/app/contracts/llm_routing_contract.py.
 */
import { z } from "zod";

export const StageIdSchema = z.enum([
  "document_ingest",
  "ontology_generation",
  "graph_build",
  "persona_generation",
  "simulation_rounds",
  "report_generation",
  "evaluation",
]);
export type StageId = z.infer<typeof StageIdSchema>;

export const ReasoningEffortSchema = z.enum(["none", "minimal", "low", "medium", "high"]);
export type ReasoningEffort = z.infer<typeof ReasoningEffortSchema>;

export const StageLLMRouteSchema = z.object({
  stage: StageIdSchema.optional().nullable(),
  provider_id: z.string().optional().nullable(),
  model: z.string().optional().nullable(),
  temperature: z.number().optional().nullable(),
  max_tokens: z.number().int().optional().nullable(),
  reasoning_effort: ReasoningEffortSchema.default("none"),
  provider_options: z.record(z.any()).default({}),
}).strict();
export type StageLLMRoute = z.infer<typeof StageLLMRouteSchema>;

export const RuntimeLlmRoutingSchema = z.object({
  global_default: StageLLMRouteSchema,
  stage_overrides: z.record(StageIdSchema, StageLLMRouteSchema).default({}),
  routing_version: z.number().int().min(1).default(1),
}).strict();
export type RuntimeLlmRouting = z.infer<typeof RuntimeLlmRoutingSchema>;

export const ProviderDescriptorSchema = z.object({
  id: z.string(),
  label: z.string(),
  type: z.enum(["ollama_local", "openai", "google", "openai_compatible"]),
  base_url: z.string().url().optional().nullable(),
  api_key_ref: z.string().optional().nullable(),
  supports_models_endpoint: z.boolean().default(false),
  fallback_models: z.array(z.string()).default([]),
}).strict();
export type ProviderDescriptor = z.infer<typeof ProviderDescriptorSchema>;

export const ResolvedRouteSchema = z.object({
  stage: StageIdSchema,
  provider_id: z.string(),
  model: z.string(),
  base_url_sanitized: z.string().optional().nullable(),
  reasoning_effort: ReasoningEffortSchema.default("none"),
  routing_version: z.number().int(),
  provider_options: z.record(z.any()).default({}),
  started_at: z.string().optional().nullable(),
}).strict();
export type ResolvedRoute = z.infer<typeof ResolvedRouteSchema>;
