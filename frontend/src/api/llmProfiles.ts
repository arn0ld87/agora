/**
 * LLM-Profile-API-Client (P5.5)
 *
 * Holt persistierte Profile aus GET /api/settings/llm-profiles.
 * Zod-strict-Parse ist Pflicht (Layer-0-Boundary).
 */
import type { LlmProfile } from '../contracts/llmProfileContract'
import { LlmProfileListResponseSchema } from '../contracts/llmProfileContract'
import service from './index'

export async function fetchLlmProfiles(): Promise<LlmProfile[]> {
  const res = await service.get('/api/settings/llm-profiles')
  // service-Interceptor packt bereits response.data aus (Envelope-Unwrap).
  // Backend-Shape: { success: true, data: { profiles: [...] } }
  const payload = (res as { data?: unknown })?.data ?? res
  const parsed = LlmProfileListResponseSchema.parse(payload)
  return parsed.profiles
}
