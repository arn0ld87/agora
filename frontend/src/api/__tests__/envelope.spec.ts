import { describe, it, expect } from 'vitest'
import { unwrap, ApiError, isApiError } from '../envelope'

describe('unwrap', () => {
  it('returns data on success envelope', () => {
    const env = { success: true as const, data: { foo: 'bar' } }
    expect(unwrap(env)).toEqual({ foo: 'bar' })
  })

  it('throws ApiError on error envelope', () => {
    const env = { success: false as const, code: 'not_found', error: 'X' }
    expect(() => unwrap(env)).toThrow(ApiError)
  })

  it('preserves code, message and details on error', () => {
    const env = {
      success: false as const,
      code: 'rate_limited',
      error: 'Too many',
      details: { retry_after: 30 }
    }
    expect.assertions(4)
    try {
      unwrap(env)
    } catch (e) {
      expect(isApiError(e)).toBe(true)
      if (isApiError(e)) {
        expect(e.code).toBe('rate_limited')
        expect(e.message).toBe('Too many')
        expect(e.details).toEqual({ retry_after: 30 })
      }
    }
  })

  it('falls back to unknown_error when code missing', () => {
    const env = { success: false as const, error: 'oops' }
    expect.assertions(2)
    try {
      unwrap(env)
    } catch (e) {
      expect(isApiError(e)).toBe(true)
      if (isApiError(e)) expect(e.code).toBe('unknown_error')
    }
  })

  it('falls back to default message when error string missing', () => {
    const env = { success: false as const, code: 'internal_error' } as const
    expect.assertions(2)
    try {
      unwrap(env)
    } catch (e) {
      expect(isApiError(e)).toBe(true)
      if (isApiError(e)) expect(e.message).toBe('Unbekannter Fehler')
    }
  })

  it('exposes the original envelope on the thrown error', () => {
    const env = { success: false as const, code: 'timeout', error: 'slow' }
    expect.assertions(2)
    try {
      unwrap(env)
    } catch (e) {
      expect(isApiError(e)).toBe(true)
      if (isApiError(e)) expect(e.originalResponse).toEqual(env)
    }
  })
})

describe('ApiError', () => {
  it('preserves typed code and status fields', () => {
    const err = new ApiError({ code: 'neo4j_unavailable', status: 503, message: 'down' })
    expect(err.code).toBe('neo4j_unavailable')
    expect(err.status).toBe(503)
    expect(err.message).toBe('down')
  })

  it('keeps prototype chain so instanceof works after transpilation', () => {
    const err = new ApiError({ code: 'x', status: 0, message: 'y' })
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toBeInstanceOf(Error)
  })
})

describe('isApiError', () => {
  it('returns true for ApiError instances', () => {
    expect(isApiError(new ApiError({ code: 'x', status: 0, message: 'y' }))).toBe(true)
  })

  it('returns false for vanilla Error', () => {
    expect(isApiError(new Error('x'))).toBe(false)
  })

  it('returns false for non-error values', () => {
    expect(isApiError('string')).toBe(false)
    expect(isApiError(null)).toBe(false)
    expect(isApiError(undefined)).toBe(false)
    expect(isApiError({ code: 'x' })).toBe(false)
  })
})
