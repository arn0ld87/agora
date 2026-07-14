/**
 * LLM Routing Contracts — Zod-Spiegel.
 *
 * Spiegelt `backend/app/contracts/llm_routing_contract.py` für die Felder,
 * die das Frontend direkt liest/schreibt. Slice 7.6c: Der frühere Stage-Route-
 * Type und sein Schema sind aus dem Frontend entfernt; die
 * Body-Struktur lebt jetzt unter `frontend/src/contracts/llmRoute.ts` als
 * `LlmRoute`/`LlmRouteSchema`. Components/Views konvertieren AiModelRef via
 * `useAiModelRefAdapter.toLlmRoute` an der Backend-Boundary.
 */
import { z } from "zod";
import { LlmRouteSchema, StageIdSchema, ReasoningEffortSchema } from "./llmRoute";

// Re-Export der Basis-Enums (Definition in ./llmRoute, um Import-Zyklen zu
// vermeiden), damit bestehende Importeure `StageId`/`ReasoningEffort` weiterhin
// aus diesem Modul beziehen können.
export { StageIdSchema, ReasoningEffortSchema } from "./llmRoute";
export type { StageId, ReasoningEffort } from "./llmRoute";

export const RuntimeLlmRoutingSchema = z.object({
  global_default: LlmRouteSchema,
  stage_overrides: z.partialRecord(StageIdSchema, LlmRouteSchema).default({}),
  routing_version: z.number().int().min(1).default(1),
}).strict();
export type RuntimeLlmRouting = z.infer<typeof RuntimeLlmRoutingSchema>;

export const ProviderDescriptorSchema = z.object({
  id: z.string(),
  label: z.string(),
  // Muss backend/app/contracts/provider_types.py::ProviderType vollständig
  // spiegeln (Drift-Fix, aufgedeckt durch Onboarding Slice 3 Task 5: GET
  // /api/llm/providers liefert Deskriptoren für alle Registry-Einträge,
  // u.a. "ollama"/"anthropic"/"minimax"/"opencode_go", nicht nur die zuvor
  // gespiegelte Teilmenge).
  type: z.enum([
    "ollama",
    "openai",
    "google",
    "anthropic",
    "custom",
    "ollama_cloud",
    "openai_compatible",
    "minimax",
    "opencode_go",
    "github_copilot",
    "cloud",
    "unknown",
  ]),
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
  provider_options: z.record(z.string(), z.any()).default({}),
  started_at: z.string().optional().nullable(),
}).strict();
export type ResolvedRoute = z.infer<typeof ResolvedRouteSchema>;

export const LlmInvocationEventSchema = z.object({
  run_id: z.string(),
  stage: z.string(),
  provider_id: z.string(),
  model: z.string(),
  base_url_sanitized: z.string().optional().nullable(),
  routing_version: z.number().int(),
  timestamp: z.number(),
  latency_ms: z.number(),
  success: z.boolean(),
  error_type: z.string().optional().nullable(),
  http_status: z.number().int().optional().nullable(),
  remote_request_id: z.string().optional().nullable(),
}).strict();
export type LlmInvocationEvent = z.infer<typeof LlmInvocationEventSchema>;
