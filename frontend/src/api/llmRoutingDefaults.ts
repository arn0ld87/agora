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

export async function getRoutingDefaults(): Promise<WorkspaceLlmRoutingDefaultsResponse> {
  const resp = await service.get<ApiSuccessEnvelope<unknown>>("/api/llm/routing/defaults");
  return unwrapAndParse(resp, WorkspaceLlmRoutingDefaultsResponseSchema);
}

export async function replaceRoutingDefaults(
  payload: WorkspaceLlmRoutingDefaults,
): Promise<WorkspaceLlmRoutingDefaultsResponse> {
  const resp = await service.put<ApiSuccessEnvelope<unknown>>(
    "/api/llm/routing/defaults",
    payload,
  );
  return unwrapAndParse(resp, WorkspaceLlmRoutingDefaultsResponseSchema);
}

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

export async function replaceGlobalDefault(
  route: LlmRoute,
): Promise<WorkspaceLlmRoutingDefaultsResponse> {
  const resp = await service.put<ApiSuccessEnvelope<unknown>>(
    "/api/llm/routing/defaults/global",
    route,
  );
  return unwrapAndParse(resp, WorkspaceLlmRoutingDefaultsResponseSchema);
}
