/**
 * supabaseClient — lazily creates ONE Supabase client from `/api/auth/config`
 * values, only when jwt_enabled is true.
 *
 * Used for auth (sign in/up/out, refresh, reset) and, with realtime_enabled,
 * as a list-invalidation signal (#1618) — never as a data source.
 * The client is cached after first creation; subsequent calls return the
 * same instance.
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js'
import type { AuthConfigResponse } from '../contracts/authConfigContract'

let _client: SupabaseClient | null = null

/**
 * Returns the lazily-initialized Supabase client.
 * Must only be called after a successful `loadConfig()` with `jwt_enabled=true`.
 */
export function getSupabaseClient(): SupabaseClient | null {
  return _client
}

/**
 * Initializes the Supabase client from the given auth config.
 * No-op if jwt_enabled is false or if called a second time.
 * Returns the client if initialized, null otherwise.
 */
export function initSupabaseClient(config: AuthConfigResponse): SupabaseClient | null {
  if (!config.jwt_enabled) return null
  if (_client) return _client
  if (!config.supabase_url || !config.supabase_anon_key) return null

  _client = createClient(config.supabase_url, config.supabase_anon_key, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
      flowType: 'pkce',
    },
  })
  return _client
}

/**
 * Resets the cached client. Only used in tests.
 */
export function _resetSupabaseClient(): void {
  _client = null
}
