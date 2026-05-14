/**
 * LLM-Profile-API-Client (P5.4)
 *
 * GET/POST/PUT/DELETE /api/settings/llm-profiles
 * Zod-strict-Parse ist Pflicht (Layer-0-Boundary).
 */
import type { LlmProfile, LlmProfileCreateRequest } from '../contracts/llmProfileContract'
import { LlmProfileListResponseSchema, LlmProfileSchema } from '../contracts/llmProfileContract'
import service from './index'

export async function fetchLlmProfiles(): Promise<LlmProfile[]> {
  const res = await service.get('/api/settings/llm-profiles')
  // service-Interceptor packt bereits response.data aus (Envelope-Unwrap).
  // Backend-Shape: { success: true, data: { profiles: [...] } }
  const payload = (res as { data?: unknown })?.data ?? res
  const parsed = LlmProfileListResponseSchema.parse(payload)
  return parsed.profiles
}

export async function createLlmProfile(req: LlmProfileCreateRequest): Promise<LlmProfile> {
  const res = await service.post('/api/settings/llm-profiles', req)
  const payload = (res as { data?: unknown })?.data ?? res
  return LlmProfileSchema.parse(payload)
}

export async function updateLlmProfile(id: string, req: LlmProfileCreateRequest): Promise<LlmProfile> {
  const res = await service.put(`/api/settings/llm-profiles/${id}`, req)
  const payload = (res as { data?: unknown })?.data ?? res
  return LlmProfileSchema.parse(payload)
}

export async function deleteLlmProfile(id: string): Promise<void> {
  await service.delete(`/api/settings/llm-profiles/${id}`)
}

export async function setDefaultLlmProfile(id: string): Promise<LlmProfile> {
  const res = await service.post(`/api/settings/llm-profiles/${id}/default`)
  const payload = (res as { data?: unknown })?.data ?? res
  return LlmProfileSchema.parse(payload)
}
