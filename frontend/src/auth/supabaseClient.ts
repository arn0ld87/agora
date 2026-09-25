/**
 * supabaseClient — lazily creates ONE Supabase client from `/api/auth/config`
 * values, only when jwt_enabled is true.
 *
 * Used ONLY for auth (sign in/up/out, refresh, reset) — never for data.
 * The client is cached after first creation; subsequent calls return the
 * same instance.
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js'
import type { AuthConfigResponse } from '../contracts/authConfigContract'

let _client: SupabaseClient | null = null

/**
 * Fester Speicherschlüssel der Supabase-Session. Mit ihm lässt sich die
 * gespeicherte Session ohne Netzaufruf verwerfen (siehe clearPersistedSession).
 */
export const SUPABASE_STORAGE_KEY = 'agora-supabase-auth'

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
      storageKey: SUPABASE_STORAGE_KEY,
    },
  })
  return _client
}

/**
 * Entfernt die gespeicherte Session aus localStorage, ohne GoTrue anzufragen.
 * Für den Fall, dass `auth.signOut()` wirft: dann hat supabase-js die Session
 * nicht entfernt, und ein Neuladen stellte sie wieder her.
 */
export function clearPersistedSession(): void {
  for (const suffix of ['', '-code-verifier', '-user']) {
    try {
      globalThis.localStorage?.removeItem(`${SUPABASE_STORAGE_KEY}${suffix}`)
    } catch {
      // Speicher gesperrt (privater Modus): nichts zu entfernen.
    }
  }
}

/**
 * Resets the cached client. Only used in tests.
 */
export function _resetSupabaseClient(): void {
  _client = null
}
