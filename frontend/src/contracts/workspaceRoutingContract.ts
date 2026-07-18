/**
 * Workspace-Routing-Defaults — Zod-Spiegel.
 *
 * Spiegelt `backend/app/contracts/workspace_routing_contract.py`. Slice 7.6c:
 * Body-Typ ist `LlmRouteSchema` (früherer Stage-Route-Type entfernt).
 */
import { z } from "zod";
import { StageIdSchema } from "./llmRoutingContract";
import { LlmRouteSchema } from "./llmRoute";
import { AiRouteSchema } from "./aiProviderContract";

export const WorkspaceLlmRoutingDefaultsSchema = z
  .object({
    global_default: LlmRouteSchema,
    stage_overrides: z.partialRecord(StageIdSchema, LlmRouteSchema).default({}),
    updated_at: z.string().nullable().optional(),
    version: z.number().int().min(1).default(1),
  })
  .strict();
export type WorkspaceLlmRoutingDefaults = z.infer<typeof WorkspaceLlmRoutingDefaultsSchema>;

/**
 * Response-Variante des Vertrags: Das Backend reichert JEDE
 * `/api/llm/routing/defaults*`-Antwort über `_with_ai_route()`
 * (backend/app/api/llm_routing.py) um einen aufgelösten `ai_route`-Block an.
 * Diese Anreicherung ist rein additiv und gehört nicht zum gespeicherten
 * Modell — deshalb ein eigenes, streng bleibendes Response-Schema, statt den
 * Store-Contract aufzuweichen. Ohne dieses Feld bricht `unwrapAndParse` mit
 * `unrecognized_keys: ["ai_route"]` ab und die LlmProvidersView crasht beim
 * Laden und beim Speichern des Workspace-Defaults.
 */
export const WorkspaceLlmRoutingDefaultsResponseSchema =
  WorkspaceLlmRoutingDefaultsSchema.extend({
    ai_route: AiRouteSchema.optional(),
  });
export type WorkspaceLlmRoutingDefaultsResponse = z.infer<
  typeof WorkspaceLlmRoutingDefaultsResponseSchema
>;
