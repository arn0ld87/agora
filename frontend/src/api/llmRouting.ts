import service from "./index";
import {
  ProviderDescriptor,
  RuntimeLlmRouting,
  ResolvedRoute,
  LlmInvocationEvent,
} from "../contracts/llmRoutingContract";
import type { LlmRoute } from "../contracts/llmRoute";
import type { AiRoute } from "../contracts/aiProviderContract";
import { ApiSuccessEnvelope } from "./envelope";

export interface RunLlmRoutingResponse {
  /** @deprecated Use `ai_route`; retained for v3 consumers. */
  runtime_config: RuntimeLlmRouting;
  /** @deprecated Use the canonical route snapshot; retained for v3 consumers. */
  snapshots: Record<string, ResolvedRoute>;
  invocation_events: LlmInvocationEvent[];
  ai_route: AiRoute;
}

export interface RuntimeLlmRoutingResponse {
  /** @deprecated Use `ai_route`; retained for v3 consumers. */
  global_default: RuntimeLlmRouting["global_default"];
  /** @deprecated Use `ai_route`; retained for v3 consumers. */
  stage_overrides: RuntimeLlmRouting["stage_overrides"];
  /** @deprecated Retained for v3 consumers. */
  routing_version: RuntimeLlmRouting["routing_version"];
  ai_route: AiRoute;
}

export async function listLlmProviders(): Promise<ProviderDescriptor[]> {
  const resp =
    await service.get<ApiSuccessEnvelope<ProviderDescriptor[]>>(
      "/api/llm/providers",
    );
  return (resp as any).data;
}

export async function listProviderModels(
  providerId: string,
  baseUrl?: string,
): Promise<any[]> {
  const query = baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : "";
  const resp = await service.get<ApiSuccessEnvelope<any[]>>(
    `/api/llm/providers/${providerId}/models${query}`,
  );
  return (resp as any).data;
}

export async function getRunLlmRouting(
  runId: string,
): Promise<RunLlmRoutingResponse> {
  const resp = await service.get<ApiSuccessEnvelope<RunLlmRoutingResponse>>(
    `/api/runs/${runId}/llm-routing`,
  );
  return (resp as any).data;
}

export async function updateRunLlmRouting(
  runId: string,
  config: RuntimeLlmRouting,
): Promise<RuntimeLlmRoutingResponse> {
  const resp = await service.put<ApiSuccessEnvelope<RuntimeLlmRoutingResponse>>(
    `/api/runs/${runId}/llm-routing`,
    config,
  );
  return (resp as any).data;
}

export async function patchStageLlmRouting(
  runId: string,
  stageId: string,
  route: LlmRoute,
): Promise<RuntimeLlmRoutingResponse> {
  const resp = await service.patch<
    ApiSuccessEnvelope<RuntimeLlmRoutingResponse>
  >(`/api/runs/${runId}/llm-routing/stages/${stageId}`, route);
  return (resp as any).data;
}

export interface ActiveLlmConfig {
  provider_id?: string;
  model?: string;
  /** Server-managed; returned by GET, never sent by clients. */
  base_url?: string;
}

export interface ActiveLlmConfigUpdate {
  provider_id: string;
  model: string;
}

export async function getActiveLlmConfig(): Promise<ActiveLlmConfig> {
  const resp = await service.get<ApiSuccessEnvelope<ActiveLlmConfig>>(
    "/api/llm/active-config",
  );
  return (resp as any).data || {};
}

export async function setActiveLlmConfig(
  cfg: ActiveLlmConfigUpdate,
): Promise<ActiveLlmConfig> {
  const payload: ActiveLlmConfigUpdate = {
    provider_id: cfg.provider_id,
    model: cfg.model,
  };
  const resp = await service.put<ApiSuccessEnvelope<ActiveLlmConfig>>(
    "/api/llm/active-config",
    payload,
  );
  return (resp as any).data;
}
