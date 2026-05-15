/**
 * LLM-Provider-API-Keys — HTTP-Client.
 *
 * Bedient die in backend/app/api/llm_providers.py ergänzten CRUD-Endpunkte
 * für persistierte (Fernet-verschlüsselte) Provider-Keys.
 */
import service from "./index";
import {
  LlmProviderKeyCreateRequest,
  LlmProviderKeyCreateRequestSchema,
  LlmProviderKeyEntry,
  LlmProviderKeyEntrySchema,
  LlmProviderKeysListResponse,
  LlmProviderKeysListResponseSchema,
} from "../contracts/llmProviderKeysContract";
import { ApiSuccessEnvelope } from "./envelope";

export async function listLlmProviderKeys(): Promise<LlmProviderKeysListResponse> {
  const resp = await service.get<ApiSuccessEnvelope<unknown>>("/api/llm/providers/api-keys");
  return LlmProviderKeysListResponseSchema.parse((resp as unknown as { data: unknown }).data);
}

export async function getLlmProviderKey(providerId: string): Promise<LlmProviderKeyEntry> {
  const resp = await service.get<ApiSuccessEnvelope<unknown>>(
    `/api/llm/providers/${providerId}/api-key`,
  );
  return LlmProviderKeyEntrySchema.parse((resp as unknown as { data: unknown }).data);
}

export async function upsertLlmProviderKey(
  providerId: string,
  req: LlmProviderKeyCreateRequest,
  options: { validate?: boolean } = {},
): Promise<LlmProviderKeyEntry> {
  LlmProviderKeyCreateRequestSchema.parse(req);
  const query = options.validate ? "?validate=1" : "";
  const resp = await service.post<ApiSuccessEnvelope<unknown>>(
    `/api/llm/providers/${providerId}/api-key${query}`,
    req,
  );
  return LlmProviderKeyEntrySchema.parse((resp as unknown as { data: unknown }).data);
}

export async function deleteLlmProviderKey(providerId: string): Promise<void> {
  await service.delete(`/api/llm/providers/${providerId}/api-key`);
}

export interface ProviderTestResult {
  connectivity: "ok" | "failed";
  models_found?: number;
  inference?: "ok";
  response_preview?: string;
}

export async function testLlmProvider(
  providerId: string,
  payload: { base_url?: string; api_key?: string } = {},
  options: { inference?: boolean } = {},
): Promise<ProviderTestResult> {
  const query = options.inference ? "?inference=1" : "";
  const resp = await service.post<ApiSuccessEnvelope<ProviderTestResult>>(
    `/api/llm/providers/${providerId}/test${query}`,
    payload,
  );
  return (resp as unknown as { data: ProviderTestResult }).data;
}
