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
 * Fester Speicherschlüssel der Supabase-Session. Mit ihm lässt sich die
 * gespeicherte Session ohne Netzaufruf verwerfen (siehe clearPersistedSession).
 */
export const SUPABASE_STORAGE_KEY = 'agora-supabase-auth'

const STORAGE_SUFFIXES = ['', '-code-verifier', '-user'] as const

/** Standardschlüssel von supabase-js ohne `storageKey`: `sb-<ref>-auth-token`. */
function legacyStorageKey(supabaseUrl: string): string | null {
  try {
    return `sb-${new URL(supabaseUrl).hostname.split('.')[0]}-auth-token`
  } catch {
    return null
  }
}

/**
 * Übernimmt eine Session, die ältere Stände unter dem Standardschlüssel
 * gespeichert haben, auf `SUPABASE_STORAGE_KEY` und entfernt den alten
 * Eintrag. So bleibt eine angemeldete Sitzung beim Update bestehen, und
 * es liegen keine verwaisten Zugangsdaten im Speicher.
 */
function migrateLegacySession(supabaseUrl: string): void {
  const legacy = legacyStorageKey(supabaseUrl)
  if (!legacy || legacy === SUPABASE_STORAGE_KEY) return
  for (const suffix of STORAGE_SUFFIXES) {
    try {
      const storage = globalThis.localStorage
      const value = storage?.getItem(`${legacy}${suffix}`)
      if (value === null || value === undefined) continue
      if (storage.getItem(`${SUPABASE_STORAGE_KEY}${suffix}`) === null) {
        storage.setItem(`${SUPABASE_STORAGE_KEY}${suffix}`, value)
      }
      storage.removeItem(`${legacy}${suffix}`)
    } catch {
      // Speicher gesperrt (privater Modus): nichts zu übernehmen.
    }
  }
}

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

  migrateLegacySession(config.supabase_url)
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
  for (const suffix of STORAGE_SUFFIXES) {
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
