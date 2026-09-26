/** Mirrors WorkspaceAvailable* in backend/app/contracts/workspace_provider_credentials_contract.py. */
import { z } from 'zod'
import { AiModelStatusSchema } from './aiModelRef'

export const WorkspaceProviderKindSchema = z.enum([
  'ollama', 'openai', 'google', 'anthropic', 'custom', 'ollama_cloud',
  'openai_compatible', 'minimax', 'opencode_go', 'github_copilot',
  'bedrock', 'cloud', 'codex_cli', 'claude_cli', 'unknown',
])

export const WorkspaceAvailableProviderSchema = z.object({
  provider_connection_id: z.string().min(1),
  provider_kind: WorkspaceProviderKindSchema,
  display_name: z.string().min(1),
}).strict()

export const WorkspaceAvailableModelSchema = WorkspaceAvailableProviderSchema.extend({
  model_id: z.string().min(1),
  model_label: z.string().min(1),
  source: z.enum(['live', 'cached', 'fallback', 'custom']),
  status: AiModelStatusSchema,
  local_or_cloud: z.enum(['local', 'cloud']).default('cloud'),
  capabilities: z.array(z.string()).default([]),
  unsupported_capabilities: z.array(z.string()).default([]),
  context_window: z.number().int().positive().nullable().default(null),
}).strict()

export const WorkspaceAvailableModelsListSchema = z.object({
  items: z.array(WorkspaceAvailableModelSchema),
  providers: z.array(WorkspaceAvailableProviderSchema),
  total: z.number().int().nonnegative(),
}).strict().refine((value) => value.total === value.items.length, {
  message: 'Model count does not match items', path: ['total'],
})

export type WorkspaceAvailableProvider = z.infer<typeof WorkspaceAvailableProviderSchema>
export type WorkspaceAvailableModel = z.infer<typeof WorkspaceAvailableModelSchema>
export type WorkspaceAvailableModelsList = z.infer<typeof WorkspaceAvailableModelsListSchema>
