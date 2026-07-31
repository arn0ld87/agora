/**
 * llmRoute.ts — Frontend-Spiegel des Backend-Route-Body-Schemas.
 *
 * Strukturell identisch zum Route-Body in
 * `backend/app/contracts/llm_routing_contract.py`. Slice 7.6c
 * hat den Frontend-Typ bewusst aus dem v3-Vertrag entkoppelt — Components
 * und Views konvertieren AiModelRef via `useAiModelRefAdapter.toLlmRoute`
 * nur an der Backend-Boundary in diese Form.
 *
 * Das Backend bleibt Pydantic-SSoT (`RuntimeLlmRouting`).
 * Validierung im Frontend übernimmt `LlmRouteSchema` (Zod, `extra="forbid"`
 * via `.strict()`), damit das Vertragsschema weiterhin parse-fähig bleibt,
 * wenn das Frontend Routing-Defaults aus dem Backend zurückliest.
 */
import { z } from 'zod';

import { AiModelSourceSchema } from './aiModelRef';

// StageId + ReasoningEffort sind Basis-Enums, auf denen LlmRoute aufsetzt.
// Sie leben hier (unterste Vertrags-Ebene), damit `llmRoutingContract.ts`
// `LlmRouteSchema` importieren kann, ohne einen zirkulären Import zu erzeugen.
// `llmRoutingContract.ts` re-exportiert beide für bestehende Importeure.
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

export const LlmRouteSchema = z
  .object({
    stage: StageIdSchema.optional().nullable(),
    provider_id: z.string().optional().nullable(),
    model: z.string().optional().nullable(),
    temperature: z.number().optional().nullable(),
    max_tokens: z.number().int().optional().nullable(),
    reasoning_effort: ReasoningEffortSchema.default('none'),
    provider_options: z.record(z.string(), z.any()).default({}),
    // Issue #901: Das Backend fuehrt die Herkunft der Routing-Entscheidung
    // seit diesem Slice auf der StageLLMRoute mit. Ohne den Spiegel wuerde
    // `.strict()` beim Zuruecklesen von Routing-Defaults hart scheitern —
    // genau der Pfad, fuer den das strict-Schema laut Kopfkommentar existiert.
    // Optional + nullable, weil Bestandsrouten das Feld nicht tragen.
    ai_model_ref_source: AiModelSourceSchema.optional().nullable(),
    fallback_reason: z.string().optional().nullable(),
  })
  .strict();

export type LlmRoute = z.infer<typeof LlmRouteSchema>;