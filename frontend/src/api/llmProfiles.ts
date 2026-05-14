/**
 * LLM-Profile-API-Client (P5.4)
 *
 * GET/POST/PUT/DELETE /api/settings/llm-profiles
 * Zod-strict-Parse ist Pflicht (Layer-0-Boundary).
 */
import type { LlmProfile, LlmProfileCreateRequest } from '../contracts/llmProfileContract'
import { LlmProfileListResponseSchema, LlmProfileSchema } from '../contracts/llmProfileContract'
import service from './index'

// service-Interceptor packt response.data bereits aus. Backend-Shape ist
// { success: true, data: <payload> } — wir greifen darum noch eine Ebene
// tiefer, falls der Envelope durchgereicht wurde.
function unwrap(res: unknown): unknown {
  return (res as { data?: unknown })?.data ?? res
}

export async function fetchLlmProfiles(): Promise<LlmProfile[]> {
  const res = await service.get('/api/settings/llm-profiles')
  return LlmProfileListResponseSchema.parse(unwrap(res)).profiles
}

export async function createLlmProfile(req: LlmProfileCreateRequest): Promise<LlmProfile> {
  const res = await service.post('/api/settings/llm-profiles', req)
  return LlmProfileSchema.parse(unwrap(res))
}

export async function updateLlmProfile(id: string, req: LlmProfileCreateRequest): Promise<LlmProfile> {
  const res = await service.put(`/api/settings/llm-profiles/${id}`, req)
  return LlmProfileSchema.parse(unwrap(res))
}

export async function deleteLlmProfile(id: string): Promise<void> {
  await service.delete(`/api/settings/llm-profiles/${id}`)
}

export async function setDefaultLlmProfile(id: string): Promise<LlmProfile> {
  const res = await service.post(`/api/settings/llm-profiles/${id}/default`)
  return LlmProfileSchema.parse(unwrap(res))
}
