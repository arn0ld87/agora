import service from "./index";
import {
  ProviderDescriptor,
  RuntimeLlmRouting,
  ResolvedRoute,
  StageLLMRoute
} from "../contracts/llmRoutingContract";
import { SuccessEnvelope } from "./envelope";

export async function listLlmProviders(): Promise<ProviderDescriptor[]> {
  const resp = await service.get<SuccessEnvelope<ProviderDescriptor[]>>("/llm/providers");
  return (resp as any).data;
}

export async function listProviderModels(providerId: string, baseUrl?: string): Promise<any[]> {
  const query = baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : "";
  const resp = await service.get<SuccessEnvelope<any[]>>(`/llm/providers/${providerId}/models${query}`);
  return (resp as any).data;
}

export async function getRunLlmRouting(runId: string): Promise<{
  runtime_config: RuntimeLlmRouting,
  snapshots: Record<string, ResolvedRoute>
}> {
  const resp = await service.get<SuccessEnvelope<{
    runtime_config: RuntimeLlmRouting,
    snapshots: Record<string, ResolvedRoute>
  }>>(`/runs/${runId}/llm-routing`);
  return (resp as any).data;
}

export async function updateRunLlmRouting(runId: string, config: RuntimeLlmRouting): Promise<RuntimeLlmRouting> {
  const resp = await service.put<SuccessEnvelope<RuntimeLlmRouting>>(`/runs/${runId}/llm-routing`, config);
  return (resp as any).data;
}

export async function patchStageLlmRouting(runId: string, stageId: string, route: StageLLMRoute): Promise<RuntimeLlmRouting> {
  const resp = await service.patch<SuccessEnvelope<RuntimeLlmRouting>>(`/runs/${runId}/llm-routing/stages/${stageId}`, route);
  return (resp as any).data;
}
