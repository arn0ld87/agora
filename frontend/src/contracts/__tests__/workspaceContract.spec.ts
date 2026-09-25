import { describe, expect, it } from 'vitest'

import workspaceSummaryJsonSchema from '../../../../schemas/workspace-summary.schema.json'
import workspaceBootstrapRequestJsonSchema from '../../../../schemas/workspace-bootstrap-request.schema.json'
import workspaceMembershipJsonSchema from '../../../../schemas/workspace-membership.schema.json'
import workspaceMemberUpsertJsonSchema from '../../../../schemas/workspace-member-upsert.schema.json'
import workspaceMemberRemovalJsonSchema from '../../../../schemas/workspace-member-removal.schema.json'

import {
  WorkspaceRoleSchema,
  WorkspaceSummarySchema,
  WorkspaceBootstrapRequestSchema,
  WorkspaceMembershipSchema,
  WorkspaceMemberUpsertSchema,
  WorkspaceMemberRemovalSchema,
} from '../workspaceContract'

describe('workspace contracts — canonical Zod mirrors', () => {
  it('WorkspaceSummarySchema has same top-level keys as generated JSON schema', () => {
    expect(Object.keys(WorkspaceSummarySchema.shape).sort()).toEqual(
      Object.keys(workspaceSummaryJsonSchema.properties).sort(),
    )
  })

  it('WorkspaceBootstrapRequestSchema has same top-level keys as generated JSON schema', () => {
    expect(Object.keys(WorkspaceBootstrapRequestSchema.shape).sort()).toEqual(
      Object.keys(workspaceBootstrapRequestJsonSchema.properties).sort(),
    )
  })

  it('WorkspaceMembershipSchema has same top-level keys as generated JSON schema', () => {
    expect(Object.keys(WorkspaceMembershipSchema.shape).sort()).toEqual(
      Object.keys(workspaceMembershipJsonSchema.properties).sort(),
    )
  })

  it('WorkspaceMemberUpsertSchema has same top-level keys as generated JSON schema', () => {
    expect(Object.keys(WorkspaceMemberUpsertSchema.shape).sort()).toEqual(
      Object.keys(workspaceMemberUpsertJsonSchema.properties).sort(),
    )
  })

  it('WorkspaceMemberRemovalSchema has same top-level keys as generated JSON schema', () => {
    expect(Object.keys(WorkspaceMemberRemovalSchema.shape).sort()).toEqual(
      Object.keys(workspaceMemberRemovalJsonSchema.properties).sort(),
    )
  })

  it('WorkspaceMemberRemovalSchema accepts the DELETE response and rejects extra keys', () => {
    const userId = '123e4567-e89b-12d3-a456-426614174000'
    expect(WorkspaceMemberRemovalSchema.safeParse({ user_id: userId }).success).toBe(true)
    expect(WorkspaceMemberRemovalSchema.safeParse({ removed: userId }).success).toBe(false)
  })

  it('WorkspaceRoleSchema enum values match the JSON schema enum', () => {
    const schemaEnum = workspaceSummaryJsonSchema.$defs.WorkspaceRole.enum
    expect(WorkspaceRoleSchema.options).toEqual(schemaEnum)
  })

  it('WorkspaceSummarySchema accepts a valid workspace summary', () => {
    const result = WorkspaceSummarySchema.safeParse({
      workspace_id: '123e4567-e89b-12d3-a456-426614174000',
      name: 'My Workspace',
      slug: 'my-workspace',
      role: 'owner',
    })
    expect(result.success).toBe(true)
  })

  it('WorkspaceSummarySchema rejects an invalid role', () => {
    const result = WorkspaceSummarySchema.safeParse({
      workspace_id: '123e4567-e89b-12d3-a456-426614174000',
      name: 'My Workspace',
      slug: 'my-workspace',
      role: 'superadmin',
    })
    expect(result.success).toBe(false)
  })

  it('WorkspaceSummarySchema rejects extra properties (strict)', () => {
    const result = WorkspaceSummarySchema.safeParse({
      workspace_id: '123e4567-e89b-12d3-a456-426614174000',
      name: 'My Workspace',
      slug: 'my-workspace',
      role: 'member',
      extra: 'field',
    })
    expect(result.success).toBe(false)
  })

  it('WorkspaceBootstrapRequestSchema accepts empty body (name null)', () => {
    const result = WorkspaceBootstrapRequestSchema.safeParse({})
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.name).toBeNull()
    }
  })

  it('WorkspaceBootstrapRequestSchema accepts a name', () => {
    const result = WorkspaceBootstrapRequestSchema.safeParse({ name: 'New Workspace' })
    expect(result.success).toBe(true)
  })

  it('WorkspaceBootstrapRequestSchema rejects a name that is too long (>80 chars)', () => {
    const result = WorkspaceBootstrapRequestSchema.safeParse({ name: 'a'.repeat(81) })
    expect(result.success).toBe(false)
  })

  it('WorkspaceMembershipSchema accepts a valid membership', () => {
    const result = WorkspaceMembershipSchema.safeParse({
      workspace_id: '123e4567-e89b-12d3-a456-426614174000',
      user_id: '987fcdeb-51a2-43d7-8b12-345678901234',
      role: 'admin',
      created_at: '2026-01-01T00:00:00Z',
    })
    expect(result.success).toBe(true)
  })

  it('WorkspaceMemberUpsertSchema accepts a valid role', () => {
    const result = WorkspaceMemberUpsertSchema.safeParse({ role: 'viewer' })
    expect(result.success).toBe(true)
  })

  it('WorkspaceMemberUpsertSchema rejects extra properties (strict)', () => {
    const result = WorkspaceMemberUpsertSchema.safeParse({ role: 'viewer', extra: 'boom' })
    expect(result.success).toBe(false)
  })
})
