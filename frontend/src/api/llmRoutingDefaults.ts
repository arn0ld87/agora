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
  WorkspaceLlmRoutingDefaultsSchema,
} from "../contracts/workspaceRoutingContract";
import { StageId, StageLLMRoute } from "../contracts/llmRoutingContract";
import { ApiSuccessEnvelope } from "./envelope";
import { unwrapAndParse } from "./parse";

export async function getRoutingDefaults(): Promise<WorkspaceLlmRoutingDefaults> {
  const resp = await service.get<ApiSuccessEnvelope<unknown>>("/api/llm/routing/defaults");
  return unwrapAndParse(resp, WorkspaceLlmRoutingDefaultsSchema);
}

export async function replaceRoutingDefaults(
  payload: WorkspaceLlmRoutingDefaults,
): Promise<WorkspaceLlmRoutingDefaults> {
  const resp = await service.put<ApiSuccessEnvelope<unknown>>(
    "/api/llm/routing/defaults",
    payload,
  );
  return unwrapAndParse(resp, WorkspaceLlmRoutingDefaultsSchema);
}

export async function patchRoutingDefaultStage(
  stageId: StageId,
  route: StageLLMRoute | null,
): Promise<WorkspaceLlmRoutingDefaults> {
  const body = route === null ? { clear: true } : route;
  const resp = await service.patch<ApiSuccessEnvelope<unknown>>(
    `/api/llm/routing/defaults/stages/${stageId}`,
    body,
  );
  return unwrapAndParse(resp, WorkspaceLlmRoutingDefaultsSchema);
}

export async function replaceGlobalDefault(
  route: StageLLMRoute,
): Promise<WorkspaceLlmRoutingDefaults> {
  const resp = await service.put<ApiSuccessEnvelope<unknown>>(
    "/api/llm/routing/defaults/global",
    route,
  );
  return unwrapAndParse(resp, WorkspaceLlmRoutingDefaultsSchema);
}
