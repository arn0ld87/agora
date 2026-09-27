/** Mirrors backend/app/contracts/workspace_provider_credentials_contract.py. */
import { z } from 'zod'

export const WorkspaceProviderCredentialUpsertSchema = z
  .object({ api_key: z.string().min(4).max(1024) })
  .strict()
export type WorkspaceProviderCredentialUpsert = z.infer<typeof WorkspaceProviderCredentialUpsertSchema>

export const WorkspaceProviderCredentialStatusSchema = z
  .object({
    provider_id: z.string().min(1).max(64),
    configured: z.boolean(),
    updated_at: z.string().datetime({ offset: true }).nullable().default(null),
  })
  .strict()
export type WorkspaceProviderCredentialStatus = z.infer<typeof WorkspaceProviderCredentialStatusSchema>

export const WorkspaceProviderCredentialsListSchema = z
  .object({
    items: z.array(WorkspaceProviderCredentialStatusSchema),
    total: z.number().int().nonnegative(),
  })
  .strict()
export type WorkspaceProviderCredentialsList = z.infer<typeof WorkspaceProviderCredentialsListSchema>
