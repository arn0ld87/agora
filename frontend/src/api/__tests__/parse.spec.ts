/**
 * Issue #585 — centralize envelope unwrap.
 *
 * Tests for `unwrapResponse` (new) and the existing `unwrapAndParse` helpers
 * in `api/parse.ts`.
 */
import { describe, expect, it } from 'vitest'
import { z } from 'zod'
import { unwrapResponse, unwrapAndParse } from '../parse'

// ---------------------------------------------------------------------------
// unwrapResponse
// ---------------------------------------------------------------------------

describe('#585 — unwrapResponse', () => {
  it('returns the data field from a well-formed envelope', () => {
    const resp = { success: true, data: { id: 'x' } }
    expect(unwrapResponse<{ id: string }>(resp)).toEqual({ id: 'x' })
  })

  it('throws when envelope is missing the data field', () => {
    expect(() => unwrapResponse({ success: true })).toThrow(
      '[api] response envelope missing `data`',
    )
  })

  it('throws when resp is null', () => {
    expect(() => unwrapResponse(null)).toThrow('[api] response envelope missing `data`')
  })

  it('throws when resp is not an object', () => {
    expect(() => unwrapResponse(42)).toThrow('[api] response envelope missing `data`')
  })

  it('returns data even when data is falsy (0, false, "")', () => {
    expect(unwrapResponse<number>({ data: 0 })).toBe(0)
    expect(unwrapResponse<boolean>({ data: false })).toBe(false)
    expect(unwrapResponse<string>({ data: '' })).toBe('')
  })
})

// ---------------------------------------------------------------------------
// unwrapAndParse — existing helper, ensure coverage of all paths
// ---------------------------------------------------------------------------

describe('#585 — unwrapAndParse', () => {
  const schema = z.object({ id: z.string() })

  it('unwraps and validates a well-formed envelope', () => {
    const resp = { success: true, data: { id: 'abc' } }
    expect(unwrapAndParse(resp, schema)).toEqual({ id: 'abc' })
  })

  it('falls back to resp itself when no envelope wrapper is present', () => {
    const resp = { id: 'xyz' }
    expect(unwrapAndParse(resp, schema)).toEqual({ id: 'xyz' })
  })

  it('throws schema mismatch when data has wrong shape', () => {
    const resp = { success: true, data: { wrong: 42 } }
    expect(() => unwrapAndParse(resp, schema)).toThrow(/schema mismatch/i)
  })

  it('throws schema mismatch when resp is null', () => {
    expect(() => unwrapAndParse(null, schema)).toThrow(/schema mismatch/i)
  })
})
