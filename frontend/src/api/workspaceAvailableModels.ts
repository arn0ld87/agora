import service from './index'
import { unwrap, type ApiEnvelope } from './envelope'
import {
  WorkspaceAvailableModelsListSchema,
  type WorkspaceAvailableModelsList,
} from '@/contracts/workspaceAvailableModelsContract'

export async function listWorkspaceAvailableModels(): Promise<WorkspaceAvailableModelsList> {
  const envelope = (await service.get('/api/workspaces/current/available-models')) as unknown as ApiEnvelope<unknown>
  const parsed = WorkspaceAvailableModelsListSchema.safeParse(unwrap(envelope))
  if (!parsed.success) {
    throw new Error(`Invalid workspace model response: ${parsed.error.issues.map(issue => issue.path.join('.')).join(', ')}`)
  }
  return parsed.data
}
