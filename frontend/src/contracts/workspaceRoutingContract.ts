/**
 * Workspace-Routing-Defaults — Zod-Spiegel.
 *
 * Spiegelt backend/app/contracts/workspace_routing_contract.py.
 */
import { z } from "zod";
import { StageIdSchema, StageLLMRouteSchema } from "./llmRoutingContract";

export const WorkspaceLlmRoutingDefaultsSchema = z
  .object({
    global_default: StageLLMRouteSchema,
    stage_overrides: z.partialRecord(StageIdSchema, StageLLMRouteSchema).default({}),
    updated_at: z.string().nullable().optional(),
    version: z.number().int().min(1).default(1),
  })
  .strict();
export type WorkspaceLlmRoutingDefaults = z.infer<typeof WorkspaceLlmRoutingDefaultsSchema>;
