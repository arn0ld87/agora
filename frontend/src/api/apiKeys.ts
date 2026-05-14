/**
 * API-Keys — HTTP-Client-Funktionen.
 *
 * Der Axios-Interceptor in api/index.ts gibt bereits `response.data` zurück
 * (das Envelope-Objekt `{ success, data }`). Bei `success: false` wirft er
 * einen `ApiError`. Hier greifen wir auf `.data` des Envelopes zu und parsen
 * strict via Zod.
 */
import service from './index'
import {
  ApiKeyCreateRequestSchema,
  ApiKeyCreateResponseSchema,
  ApiKeyModelSchema,
  ApiKeysListResponseSchema,
  type ApiKeyCreateRequest,
  type ApiKeyCreateResponse,
  type ApiKeyModel,
  type ApiKeysListResponse,
} from '../contracts/apiKeysContract'

type Envelope<T> = { success: true; data: T }

export async function listApiKeys(): Promise<ApiKeysListResponse> {
  const envelope = await service.get('/api/api-keys') as Envelope<unknown>
  return ApiKeysListResponseSchema.parse(envelope.data)
}

export async function createApiKey(req: ApiKeyCreateRequest): Promise<ApiKeyCreateResponse> {
  ApiKeyCreateRequestSchema.parse(req)
  const envelope = await service.post('/api/api-keys', req) as Envelope<unknown>
  return ApiKeyCreateResponseSchema.parse(envelope.data)
}

export async function revokeApiKey(id: string): Promise<ApiKeyModel> {
  const envelope = await service.delete(`/api/api-keys/${id}`) as Envelope<unknown>
  return ApiKeyModelSchema.parse(envelope.data)
}
