import service from './index'
import { unwrap, type ApiEnvelope } from './envelope'
import {
  WorkspaceProviderCredentialStatusSchema,
  WorkspaceProviderCredentialsListSchema,
  type WorkspaceProviderCredentialStatus,
  type WorkspaceProviderCredentialsList,
} from '../contracts/workspaceProviderCredentialsContract'

const endpoint = '/api/workspaces/current/provider-credentials'

export async function listWorkspaceProviderCredentials(): Promise<WorkspaceProviderCredentialsList> {
  const envelope = (await service.get(endpoint)) as unknown as ApiEnvelope<unknown>
  return WorkspaceProviderCredentialsListSchema.parse(unwrap(envelope))
}

export async function saveWorkspaceProviderCredential(
  providerId: string,
  apiKey: string,
): Promise<WorkspaceProviderCredentialStatus> {
  const envelope = (await service.put(`${endpoint}/${encodeURIComponent(providerId)}`, {
    api_key: apiKey,
  })) as unknown as ApiEnvelope<unknown>
  return WorkspaceProviderCredentialStatusSchema.parse(unwrap(envelope))
}

export async function deleteWorkspaceProviderCredential(
  providerId: string,
): Promise<WorkspaceProviderCredentialStatus> {
  const envelope = (await service.delete(`${endpoint}/${encodeURIComponent(providerId)}`)) as unknown as ApiEnvelope<unknown>
  return WorkspaceProviderCredentialStatusSchema.parse(unwrap(envelope))
}
