/**
 * Issue #578 — harden Zod .parse() callsites in LLM API modules.
 *
 * Verifies that a malformed envelope (missing `data` field, schema drift)
 * results in a typed rejection rather than an unhandled exception.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const serviceMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  patch: vi.fn(),
}))

vi.mock('../index', () => ({
  default: serviceMock,
}))

import { unwrapAndParse } from '../parse'
import {
  fetchLlmProfiles,
  createLlmProfile,
  updateLlmProfile,
  setDefaultLlmProfile,
} from '../llmProfiles'
import {
  listLlmProviderKeys,
  getLlmProviderKey,
  upsertLlmProviderKey,
} from '../llmProviderKeys'
import {
  getRoutingDefaults,
  replaceRoutingDefaults,
  patchRoutingDefaultStage,
  replaceGlobalDefault,
} from '../llmRoutingDefaults'

// -------------------------------------------------------------------------
// Helpers
// -------------------------------------------------------------------------

/** Simulates a malformed response — data field is completely missing */
const missingDataEnvelope = { success: true }

/** Simulates schema drift — data has wrong shape */
const wrongShapeEnvelope = { success: true, data: { unexpected_field: 42 } }

describe('#578 — llmProfiles: safeParse replaces .parse()', () => {
  beforeEach(() => vi.clearAllMocks())

  it('rejects with typed error (not unhandled exception) when data is missing', async () => {
    serviceMock.get.mockResolvedValueOnce(missingDataEnvelope)
    await expect(fetchLlmProfiles()).rejects.toThrow(/schema mismatch/i)
  })

  it('rejects with typed error when data has wrong shape', async () => {
    serviceMock.get.mockResolvedValueOnce(wrongShapeEnvelope)
    await expect(fetchLlmProfiles()).rejects.toThrow(/schema mismatch/i)
  })

  it('rejects with typed error for createLlmProfile when data is missing', async () => {
    serviceMock.post.mockResolvedValueOnce(missingDataEnvelope)
    await expect(
      createLlmProfile({ name: 'test', provider: 'openai', base_url: 'https://api.openai.com/v1', model_name: 'gpt-4o', api_key: null, is_default: false }),
    ).rejects.toThrow(/schema mismatch/i)
  })

  it('rejects with typed error for updateLlmProfile when data has wrong shape', async () => {
    serviceMock.put.mockResolvedValueOnce(wrongShapeEnvelope)
    await expect(
      updateLlmProfile('id1', { name: 'test', provider: 'openai', base_url: 'https://api.openai.com/v1', model_name: 'gpt-4o', api_key: null, is_default: false }),
    ).rejects.toThrow(/schema mismatch/i)
  })

  it('rejects with typed error for setDefaultLlmProfile when data has wrong shape', async () => {
    serviceMock.post.mockResolvedValueOnce(wrongShapeEnvelope)
    await expect(setDefaultLlmProfile('id1')).rejects.toThrow(/schema mismatch/i)
  })
})


describe('#578 — llmProviderKeys: safeParse replaces .parse()', () => {
  beforeEach(() => vi.clearAllMocks())

  it('rejects with typed error for listLlmProviderKeys when data is missing', async () => {
    serviceMock.get.mockResolvedValueOnce(missingDataEnvelope)
    await expect(listLlmProviderKeys()).rejects.toThrow(/schema mismatch/i)
  })

  it('rejects with typed error for getLlmProviderKey when data has wrong shape', async () => {
    serviceMock.get.mockResolvedValueOnce(wrongShapeEnvelope)
    await expect(getLlmProviderKey('openai')).rejects.toThrow(/schema mismatch/i)
  })

  it('rejects with typed error for upsertLlmProviderKey response when data is missing', async () => {
    serviceMock.post.mockResolvedValueOnce(missingDataEnvelope)
    await expect(
      upsertLlmProviderKey('openai', { api_key: 'sk-test' }),
    ).rejects.toThrow(/schema mismatch/i)
  })
})

describe('#578 — llmRoutingDefaults: safeParse replaces .parse()', () => {
  beforeEach(() => vi.clearAllMocks())

  it('rejects with typed error for getRoutingDefaults when data is missing', async () => {
    serviceMock.get.mockResolvedValueOnce(missingDataEnvelope)
    await expect(getRoutingDefaults()).rejects.toThrow(/schema mismatch/i)
  })

  it('rejects with typed error for replaceRoutingDefaults when data has wrong shape', async () => {
    serviceMock.put.mockResolvedValueOnce(wrongShapeEnvelope)
    await expect(replaceRoutingDefaults({} as any)).rejects.toThrow(/schema mismatch/i)
  })

  it('rejects with typed error for patchRoutingDefaultStage when data is missing', async () => {
    serviceMock.patch.mockResolvedValueOnce(missingDataEnvelope)
    await expect(
      patchRoutingDefaultStage('graph_build' as any, null),
    ).rejects.toThrow(/schema mismatch/i)
  })

  it('rejects with typed error for replaceGlobalDefault when data has wrong shape', async () => {
    serviceMock.put.mockResolvedValueOnce(wrongShapeEnvelope)
    await expect(replaceGlobalDefault({} as any)).rejects.toThrow(/schema mismatch/i)
  })
})

// -------------------------------------------------------------------------
// #3382999388 — unwrapAndParse: already-unwrapped (envelope-free) response
// -------------------------------------------------------------------------
import { z } from 'zod'

describe('#578 — unwrapAndParse: tolerant envelope handling', () => {
  const schema = z.object({ id: z.string() })

  it('unwraps data field when response has envelope shape', () => {
    const resp = { success: true, data: { id: 'abc' } }
    expect(unwrapAndParse(resp, schema)).toEqual({ id: 'abc' })
  })

  it('falls back to resp itself when no data key present (already-unwrapped response)', () => {
    // Simulates old llmProfiles.ts unwrap-fallback: the caller already stripped
    // the envelope and passes { id: 'xyz' } directly.
    const resp = { id: 'xyz' }
    expect(unwrapAndParse(resp, schema)).toEqual({ id: 'xyz' })
  })

  it('rejects when resp is null', () => {
    expect(() => unwrapAndParse(null, schema)).toThrow(/schema mismatch/i)
  })

  it('rejects when data exists but has wrong shape', () => {
    const resp = { success: true, data: { wrong: 42 } }
    expect(() => unwrapAndParse(resp, schema)).toThrow(/schema mismatch/i)
  })
})
