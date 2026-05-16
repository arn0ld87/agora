import service from "./index";
import {
  ProviderDescriptor,
  RuntimeLlmRouting,
  ResolvedRoute,
  StageLLMRoute,
  LlmInvocationEvent,
} from "../contracts/llmRoutingContract";
import { ApiSuccessEnvelope } from "./envelope";

export async function listLlmProviders(): Promise<ProviderDescriptor[]> {
  const resp = await service.get<ApiSuccessEnvelope<ProviderDescriptor[]>>("/api/llm/providers");
  return (resp as any).data;
}

export async function listProviderModels(providerId: string, baseUrl?: string): Promise<any[]> {
  const query = baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : "";
  const resp = await service.get<ApiSuccessEnvelope<any[]>>(`/api/llm/providers/${providerId}/models${query}`);
  return (resp as any).data;
}

export async function getRunLlmRouting(runId: string): Promise<{
  runtime_config: RuntimeLlmRouting,
  snapshots: Record<string, ResolvedRoute>,
  invocation_events: LlmInvocationEvent[],
}> {
  const resp = await service.get<ApiSuccessEnvelope<{
    runtime_config: RuntimeLlmRouting,
    snapshots: Record<string, ResolvedRoute>,
    invocation_events: LlmInvocationEvent[],
  }>>(`/api/runs/${runId}/llm-routing`);
  return (resp as any).data;
}

export async function updateRunLlmRouting(runId: string, config: RuntimeLlmRouting): Promise<RuntimeLlmRouting> {
  const resp = await service.put<ApiSuccessEnvelope<RuntimeLlmRouting>>(`/api/runs/${runId}/llm-routing`, config);
  return (resp as any).data;
}

export async function patchStageLlmRouting(runId: string, stageId: string, route: StageLLMRoute): Promise<RuntimeLlmRouting> {
  const resp = await service.patch<ApiSuccessEnvelope<RuntimeLlmRouting>>(`/api/runs/${runId}/llm-routing/stages/${stageId}`, route);
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
  const resp = await service.get<ApiSuccessEnvelope<ActiveLlmConfig>>("/api/llm/active-config");
  return (resp as any).data || {};
}

export async function setActiveLlmConfig(cfg: ActiveLlmConfigUpdate): Promise<ActiveLlmConfig> {
  const payload: ActiveLlmConfigUpdate = {
    provider_id: cfg.provider_id,
    model: cfg.model,
  };
  const resp = await service.put<ApiSuccessEnvelope<ActiveLlmConfig>>("/api/llm/active-config", payload);
  return (resp as any).data;
}
