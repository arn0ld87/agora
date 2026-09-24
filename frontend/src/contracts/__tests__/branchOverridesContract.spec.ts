/**
 * Branch-Override-Contract — Zod-Spiegel-Tests (Issue #886).
 *
 * Backend-Quelle: backend/app/contracts/branch_request_contract.py
 * Schema: schemas/branch-overrides.schema.json
 */
import { describe, it, expect } from 'vitest'

import branchOverridesJsonSchema from '../../../../schemas/branch-overrides.schema.json'
import { BranchAiModelRefSchema, BranchOverridesBaseSchema, BranchOverridesSchema } from '../branchOverrides'

describe('BranchOverrides contract', () => {
  it('keeps Zod top-level fields aligned with the generated Pydantic schema', () => {
    expect(Object.keys(BranchOverridesBaseSchema.shape).sort()).toEqual(
      Object.keys(branchOverridesJsonSchema.properties).sort(),
    )
  })

  it('accepts a valid legacy llm_model override', () => {
    const result = BranchOverridesSchema.safeParse({ llm_model: 'gpt-4o-mini' })
    expect(result.success).toBe(true)
  })

  it('accepts a valid canonical ai_model_ref override', () => {
    const result = BranchOverridesSchema.safeParse({
      ai_model_ref: {
        provider_connection_id: 'conn-a',
        model_id: 'gpt-4o',
        source: 'explicit',
      },
    })
    expect(result.success).toBe(true)
  })

  it('rejects ai_model_ref combined with a non-empty llm_model', () => {
    const result = BranchOverridesSchema.safeParse({
      llm_model: 'gpt-4o-mini',
      ai_model_ref: {
        provider_connection_id: 'conn-a',
        model_id: 'gpt-4o',
        source: 'explicit',
      },
    })
    expect(result.success).toBe(false)
  })

  it('rejects an unknown top-level key', () => {
    const result = BranchOverridesSchema.safeParse({ totally_made_up: 'x' })
    expect(result.success).toBe(false)
  })

  it('rejects an ai_model_ref missing provider_connection_id', () => {
    const result = BranchAiModelRefSchema.safeParse({ model_id: 'gpt-4o' })
    expect(result.success).toBe(false)
  })
})
