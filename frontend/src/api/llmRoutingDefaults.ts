/**
 * Workspace-Routing-Defaults — HTTP-Client.
 *
 * Bedient die in backend/app/api/llm_routing.py ergänzten Defaults-Endpunkte.
 */
import service from "./index";
import {
  WorkspaceLlmRoutingDefaults,
  WorkspaceLlmRoutingDefaultsSchema,
} from "../contracts/workspaceRoutingContract";
import { StageId, StageLLMRoute } from "../contracts/llmRoutingContract";
import { ApiSuccessEnvelope } from "./envelope";

export async function getRoutingDefaults(): Promise<WorkspaceLlmRoutingDefaults> {
  const resp = await service.get<ApiSuccessEnvelope<unknown>>("/api/llm/routing/defaults");
  return WorkspaceLlmRoutingDefaultsSchema.parse((resp as unknown as { data: unknown }).data);
}

export async function replaceRoutingDefaults(
  payload: WorkspaceLlmRoutingDefaults,
): Promise<WorkspaceLlmRoutingDefaults> {
  const resp = await service.put<ApiSuccessEnvelope<unknown>>(
    "/api/llm/routing/defaults",
    payload,
  );
  return WorkspaceLlmRoutingDefaultsSchema.parse((resp as unknown as { data: unknown }).data);
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
  return WorkspaceLlmRoutingDefaultsSchema.parse((resp as unknown as { data: unknown }).data);
}

export async function replaceGlobalDefault(
  route: StageLLMRoute,
): Promise<WorkspaceLlmRoutingDefaults> {
  const resp = await service.put<ApiSuccessEnvelope<unknown>>(
    "/api/llm/routing/defaults/global",
    route,
  );
  return WorkspaceLlmRoutingDefaultsSchema.parse((resp as unknown as { data: unknown }).data);
}
