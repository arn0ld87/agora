/**
 * Workspace-Routing-Defaults — Zod-Spiegel.
 *
 * Spiegelt `backend/app/contracts/workspace_routing_contract.py`. Slice 7.6c:
 * Body-Typ ist `LlmRouteSchema` (früherer Stage-Route-Type entfernt).
 */
import { z } from "zod";
import { StageIdSchema } from "./llmRoutingContract";
import { LlmRouteSchema } from "./llmRoute";

export const WorkspaceLlmRoutingDefaultsSchema = z
  .object({
    global_default: LlmRouteSchema,
    stage_overrides: z.partialRecord(StageIdSchema, LlmRouteSchema).default({}),
    updated_at: z.string().nullable().optional(),
    version: z.number().int().min(1).default(1),
  })
  .strict();
export type WorkspaceLlmRoutingDefaults = z.infer<typeof WorkspaceLlmRoutingDefaultsSchema>;
