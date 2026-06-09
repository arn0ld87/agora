/**
 * LLM-Profile-API-Client (P5.4)
 *
 * GET/POST/PUT/DELETE /api/settings/llm-profiles
 * Zod-strict-Parse ist Pflicht (Layer-0-Boundary).
 * Issue #578: bare .parse() replaced with unwrapAndParse (typed rejection on schema drift).
 */
import type { LlmProfile, LlmProfileCreateRequest } from '../contracts/llmProfileContract'
import { LlmProfileListResponseSchema, LlmProfileSchema } from '../contracts/llmProfileContract'
import service from './index'
import { unwrapAndParse } from './parse'

export async function fetchLlmProfiles(): Promise<LlmProfile[]> {
  const res = await service.get('/api/settings/llm-profiles')
  return unwrapAndParse(res, LlmProfileListResponseSchema).profiles
}

export async function createLlmProfile(req: LlmProfileCreateRequest): Promise<LlmProfile> {
  const res = await service.post('/api/settings/llm-profiles', req)
  return unwrapAndParse(res, LlmProfileSchema)
}

export async function updateLlmProfile(id: string, req: LlmProfileCreateRequest): Promise<LlmProfile> {
  const res = await service.put(`/api/settings/llm-profiles/${id}`, req)
  return unwrapAndParse(res, LlmProfileSchema)
}

export async function deleteLlmProfile(id: string): Promise<void> {
  await service.delete(`/api/settings/llm-profiles/${id}`)
}

export async function setDefaultLlmProfile(id: string): Promise<LlmProfile> {
  const res = await service.post(`/api/settings/llm-profiles/${id}/default`)
  return unwrapAndParse(res, LlmProfileSchema)
}
