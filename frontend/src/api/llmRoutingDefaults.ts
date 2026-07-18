/**
 * Workspace-Routing-Defaults — HTTP-Client.
 *
 * Bedient die in backend/app/api/llm_routing.py ergänzten Defaults-Endpunkte.
 */
/**
 * Issue #578: bare .parse() replaced with unwrapAndParse (typed rejection on schema drift).
 */
import service from "./index";
import {
  WorkspaceLlmRoutingDefaults,
  WorkspaceLlmRoutingDefaultsResponse,
  WorkspaceLlmRoutingDefaultsResponseSchema,
} from "../contracts/workspaceRoutingContract";
import { StageId } from "../contracts/llmRoutingContract";
import type { LlmRoute } from "../contracts/llmRoute";
import { ApiSuccessEnvelope } from "./envelope";
import { unwrapAndParse } from "./parse";

/**
 * Retrieves the workspace's LLM routing defaults.
 *
 * @returns The validated workspace LLM routing defaults.
 */
export async function getRoutingDefaults(): Promise<WorkspaceLlmRoutingDefaultsResponse> {
  const resp = await service.get<ApiSuccessEnvelope<unknown>>("/api/llm/routing/defaults");
  return unwrapAndParse(resp, WorkspaceLlmRoutingDefaultsResponseSchema);
}

/**
 * Replaces the workspace's LLM routing defaults.
 *
 * @param payload - The routing defaults to apply
 * @returns The updated workspace LLM routing defaults
 */
export async function replaceRoutingDefaults(
  payload: WorkspaceLlmRoutingDefaults,
): Promise<WorkspaceLlmRoutingDefaultsResponse> {
  const resp = await service.put<ApiSuccessEnvelope<unknown>>(
    "/api/llm/routing/defaults",
    payload,
  );
  return unwrapAndParse(resp, WorkspaceLlmRoutingDefaultsResponseSchema);
}

/**
 * Updates the routing default for a stage.
 *
 * @param stageId - The stage whose routing default to update
 * @param route - The route to assign, or `null` to clear the stage default
 * @returns The updated workspace LLM routing defaults
 */
export async function patchRoutingDefaultStage(
  stageId: StageId,
  route: LlmRoute | null,
): Promise<WorkspaceLlmRoutingDefaultsResponse> {
  const body = route === null ? { clear: true } : route;
  const resp = await service.patch<ApiSuccessEnvelope<unknown>>(
    `/api/llm/routing/defaults/stages/${stageId}`,
    body,
  );
  return unwrapAndParse(resp, WorkspaceLlmRoutingDefaultsResponseSchema);
}

/**
 * Replaces the workspace-wide default LLM route.
 *
 * @returns The updated workspace LLM routing defaults.
 */
export async function replaceGlobalDefault(
  route: LlmRoute,
): Promise<WorkspaceLlmRoutingDefaultsResponse> {
  const resp = await service.put<ApiSuccessEnvelope<unknown>>(
    "/api/llm/routing/defaults/global",
    route,
  );
  return unwrapAndParse(resp, WorkspaceLlmRoutingDefaultsResponseSchema);
}
