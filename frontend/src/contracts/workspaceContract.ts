/**
 * Canonical Zod mirrors of backend/app/contracts/workspace_contract.py.
 *
 * Mirrors:
 *   - WorkspaceRole        (enum)
 *   - WorkspaceSummary     (GET /api/workspaces — workspace-summary.schema.json)
 *   - WorkspaceBootstrapRequest (POST /api/workspaces/bootstrap — workspace-bootstrap-request.schema.json)
 *   - WorkspaceMembership  (workspace-membership.schema.json)
 *   - WorkspaceMemberUpsert (workspace-member-upsert.schema.json)
 *   - WorkspaceMemberRemoval (DELETE …/members/<user_id> — workspace-member-removal.schema.json)
 */
import { z } from 'zod'

export const WorkspaceRoleSchema = z.enum(['owner', 'admin', 'member', 'viewer'])
export type WorkspaceRole = z.infer<typeof WorkspaceRoleSchema>

export const WorkspaceSummarySchema = z
  .object({
    workspace_id: z.string().uuid(),
    name: z.string(),
    slug: z.string(),
    role: WorkspaceRoleSchema,
  })
  .strict()
export type WorkspaceSummary = z.infer<typeof WorkspaceSummarySchema>

export const WorkspaceBootstrapRequestSchema = z
  .object({
    name: z.string().min(1).max(80).nullable().default(null),
  })
  .strict()
export type WorkspaceBootstrapRequest = z.infer<typeof WorkspaceBootstrapRequestSchema>

export const WorkspaceMembershipSchema = z
  .object({
    workspace_id: z.string().uuid(),
    user_id: z.string().uuid(),
    role: WorkspaceRoleSchema,
    created_at: z.string().datetime({ offset: true }),
  })
  .strict()
export type WorkspaceMembership = z.infer<typeof WorkspaceMembershipSchema>

export const WorkspaceMemberUpsertSchema = z
  .object({
    role: WorkspaceRoleSchema,
  })
  .strict()
export type WorkspaceMemberUpsert = z.infer<typeof WorkspaceMemberUpsertSchema>

export const WorkspaceMemberRemovalSchema = z
  .object({
    user_id: z.string().uuid(),
  })
  .strict()
export type WorkspaceMemberRemoval = z.infer<typeof WorkspaceMemberRemovalSchema>
