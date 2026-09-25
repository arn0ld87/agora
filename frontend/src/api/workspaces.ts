/**
 * Auth-Konfiguration und Workspaces (#1617) über den gemeinsamen
 * Envelope-Vertrag: `unwrap()` plus Zod-Parse der kanonischen Spiegel.
 */
import { z } from 'zod'
import service from './index'
import { unwrap, type ApiEnvelope } from './envelope'
import { AuthConfigResponseSchema, type AuthConfigResponse } from '../contracts/authConfigContract'
import { WorkspaceSummarySchema, type WorkspaceSummary } from '../contracts/workspaceContract'

export async function fetchAuthConfig(): Promise<AuthConfigResponse> {
  const envelope = (await service.get('/api/auth/config')) as unknown as ApiEnvelope<unknown>
  return AuthConfigResponseSchema.parse(unwrap(envelope))
}

export async function listWorkspaces(): Promise<WorkspaceSummary[]> {
  const envelope = (await service.get('/api/workspaces')) as unknown as ApiEnvelope<unknown>
  return z.array(WorkspaceSummarySchema).parse(unwrap(envelope))
}

export async function bootstrapWorkspace(): Promise<WorkspaceSummary> {
  const envelope = (await service.post('/api/workspaces/bootstrap', {})) as unknown as ApiEnvelope<unknown>
  return WorkspaceSummarySchema.parse(unwrap(envelope))
}
