/**
 * LLM-Provider-API-Keys — HTTP-Client.
 *
 * Bedient die in backend/app/api/llm_providers.py ergänzten CRUD-Endpunkte
 * für persistierte (Fernet-verschlüsselte) Provider-Keys.
 */
// Issue #578: bare .parse() replaced with unwrapAndParse (typed rejection on schema drift).
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
import { unwrapAndParse } from "./parse";

export async function listLlmProviderKeys(): Promise<LlmProviderKeysListResponse> {
  const resp = await service.get<ApiSuccessEnvelope<unknown>>("/api/llm/providers/api-keys");
  return unwrapAndParse(resp, LlmProviderKeysListResponseSchema);
}

export async function getLlmProviderKey(providerId: string): Promise<LlmProviderKeyEntry> {
  const resp = await service.get<ApiSuccessEnvelope<unknown>>(
    `/api/llm/providers/${providerId}/api-key`,
  );
  return unwrapAndParse(resp, LlmProviderKeyEntrySchema);
}

export async function upsertLlmProviderKey(
  providerId: string,
  req: LlmProviderKeyCreateRequest,
  options: { validate?: boolean } = {},
): Promise<LlmProviderKeyEntry> {
  const reqParsed = LlmProviderKeyCreateRequestSchema.safeParse(req);
  if (!reqParsed.success) {
    console.warn('[api] upsertLlmProviderKey request validation failed', reqParsed.error.flatten())
    throw new Error(`schema mismatch: ${reqParsed.error.message}`)
  }
  const query = options.validate ? "?validate=1" : "";
  const resp = await service.post<ApiSuccessEnvelope<unknown>>(
    `/api/llm/providers/${providerId}/api-key${query}`,
    req,
  );
  return unwrapAndParse(resp, LlmProviderKeyEntrySchema);
}

export async function deleteLlmProviderKey(providerId: string): Promise<void> {
  await service.delete(`/api/llm/providers/${providerId}/api-key`);
}

/**
 * Prüft ob für einen Provider ein API-Key in der Settings-DB hinterlegt ist.
 * Gibt `true` zurück wenn ein Key vorhanden ist, sonst `false`.
 * Schlägt nie mit einer Exception fehl — bei Fehler wird `false` zurückgegeben.
 */
export async function checkLlmProviderHasKey(providerId: string): Promise<boolean> {
  try {
    const resp = await service.get<{ data: { has_key: boolean } }>(
      `/api/llm/providers/${providerId}/has-key`,
    );
    return Boolean((resp as unknown as { data: { has_key: boolean } }).data?.has_key);
  } catch {
    return false;
  }
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
