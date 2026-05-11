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
  const resp = await service.get<ApiSuccessEnvelope<ProviderDescriptor[]>>("/llm/providers");
  return (resp as any).data;
}

export async function listProviderModels(providerId: string, baseUrl?: string): Promise<any[]> {
  const query = baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : "";
  const resp = await service.get<ApiSuccessEnvelope<any[]>>(`/llm/providers/${providerId}/models${query}`);
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
  }>>(`/runs/${runId}/llm-routing`);
  return (resp as any).data;
}

export async function updateRunLlmRouting(runId: string, config: RuntimeLlmRouting): Promise<RuntimeLlmRouting> {
  const resp = await service.put<ApiSuccessEnvelope<RuntimeLlmRouting>>(`/runs/${runId}/llm-routing`, config);
  return (resp as any).data;
}

export async function patchStageLlmRouting(runId: string, stageId: string, route: StageLLMRoute): Promise<RuntimeLlmRouting> {
  const resp = await service.patch<ApiSuccessEnvelope<RuntimeLlmRouting>>(`/runs/${runId}/llm-routing/stages/${stageId}`, route);
  return (resp as any).data;
}
