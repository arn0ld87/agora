/**
 * providerConnections — HTTP-Client für den kanonischen Provider-Connection-Lifecycle.
 *
 * Bedient backend/app/api/llm_providers.py `/api/llm/provider-connections*`
 * (Task 4 der Onboarding-Provider-Unification). Jede Response-Grenze wird mit
 * den Zod-Schemas aus contracts/aiProviderContract validiert (Zod-First,
 * siehe CLAUDE.md) — kein `?.`-Durchreichen bei Schema-Drift.
 *
 * `api_key` verlässt diesen Client ausschließlich als Teil des PUT-Bodys.
 * Responses enthalten laut Backend-Contract nie einen Klartext-Key; dieser
 * Client liest ihn auch nie aus einer Response und hält ihn nie im Pinia-State.
 */
import { z } from "zod";
import service from "./index";
import {
  AiModel,
  AiModelSchema,
  ProviderConnection,
  ProviderConnectionResponseSchema,
  ProviderConnectionsListResponse,
  ProviderConnectionsListResponseSchema,
  ProviderConnectionTestResult,
  ProviderConnectionTestResultSchema,
} from "../contracts/aiProviderContract";
import { ApiSuccessEnvelope } from "./envelope";
import { unwrapAndParse } from "./parse";

const AiModelListSchema = z.array(AiModelSchema);

/** PUT-Body; `api_key` bleibt optional und wird nur bei Änderung gesendet. */
export interface ProviderConnectionUpsertPayload {
  display_name: string;
  provider_kind: string;
  base_url?: string | null;
  enabled?: boolean;
  api_key?: string | null;
}

export async function listProviderConnections(): Promise<ProviderConnectionsListResponse> {
  const resp = await service.get<ApiSuccessEnvelope<unknown>>("/api/llm/provider-connections");
  return unwrapAndParse(resp, ProviderConnectionsListResponseSchema);
}

export async function upsertProviderConnection(
  connectionId: string,
  payload: ProviderConnectionUpsertPayload,
): Promise<ProviderConnection> {
  const resp = await service.put<ApiSuccessEnvelope<unknown>>(
    `/api/llm/provider-connections/${connectionId}`,
    payload,
  );
  return unwrapAndParse(resp, ProviderConnectionResponseSchema).connection;
}

export async function deleteProviderConnection(connectionId: string): Promise<void> {
  await service.delete(`/api/llm/provider-connections/${connectionId}`);
}

export async function testProviderConnection(
  connectionId: string,
): Promise<ProviderConnectionTestResult> {
  const resp = await service.post<ApiSuccessEnvelope<unknown>>(
    `/api/llm/provider-connections/${connectionId}/test`,
  );
  return unwrapAndParse(resp, ProviderConnectionTestResultSchema);
}

export async function listProviderConnectionModels(connectionId: string): Promise<AiModel[]> {
  const resp = await service.get<ApiSuccessEnvelope<unknown>>(
    `/api/llm/provider-connections/${connectionId}/models`,
  );
  return unwrapAndParse(resp, AiModelListSchema);
}
