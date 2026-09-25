import { describe, expect, it } from 'vitest'

import authConfigJsonSchema from '../../../../schemas/auth-config-response.schema.json'
import { AuthConfigResponseSchema } from '../authConfigContract'

describe('AuthConfigResponseSchema — canonical Zod mirror', () => {
  it('has the same top-level keys as the generated JSON schema', () => {
    expect(Object.keys(AuthConfigResponseSchema.shape).sort()).toEqual(
      Object.keys(authConfigJsonSchema.properties).sort(),
    )
  })

  it('accepts a JWT-disabled response (legacy mode)', () => {
    const result = AuthConfigResponseSchema.safeParse({
      auth_backend: 'token',
      jwt_enabled: false,
    })
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.supabase_url).toBeNull()
      expect(result.data.supabase_anon_key).toBeNull()
    }
  })

  it('accepts a JWT-enabled response with url and anon key', () => {
    const result = AuthConfigResponseSchema.safeParse({
      auth_backend: 'supabase',
      jwt_enabled: true,
      supabase_url: 'https://project.supabase.co',
      supabase_anon_key: 'test-anon-key',
    })
    expect(result.success).toBe(true)
  })

  it('rejects a response missing required fields', () => {
    const result = AuthConfigResponseSchema.safeParse({
      jwt_enabled: true,
      // auth_backend missing
    })
    expect(result.success).toBe(false)
  })

  it('rejects extra properties (strict)', () => {
    const result = AuthConfigResponseSchema.safeParse({
      auth_backend: 'token',
      jwt_enabled: false,
      unexpected_field: 'boom',
    })
    expect(result.success).toBe(false)
  })
})
