/**
 * supabaseClient — fester Speicherschlüssel und Verwerfen ohne Netz (#1617).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const created = vi.hoisted(() => ({ options: [] as unknown[] }))
vi.mock('@supabase/supabase-js', () => ({
  createClient: vi.fn((_url: string, _key: string, options: unknown) => {
    created.options.push(options)
    return { auth: {} }
  }),
}))

import {
  SUPABASE_STORAGE_KEY,
  _resetSupabaseClient,
  clearPersistedSession,
  initSupabaseClient,
} from '../supabaseClient'

beforeEach(() => {
  localStorage.clear()
  created.options.length = 0
  _resetSupabaseClient()
})

describe('supabaseClient', () => {
  it('legt die Session unter dem festen Schlüssel ab', () => {
    initSupabaseClient({
      auth_backend: 'hybrid',
      jwt_enabled: true,
      supabase_url: 'https://s.test',
      supabase_anon_key: 'k',
      realtime_enabled: false,
    })
    expect(created.options[0]).toMatchObject({ auth: { storageKey: SUPABASE_STORAGE_KEY } })
  })

  it('verwirft die gespeicherte Session ohne Netzaufruf, fremde Schlüssel bleiben', () => {
    localStorage.setItem(SUPABASE_STORAGE_KEY, '{"access_token":"x"}')
    localStorage.setItem(`${SUPABASE_STORAGE_KEY}-code-verifier`, 'v')
    localStorage.setItem(`${SUPABASE_STORAGE_KEY}-user`, '{}')
    localStorage.setItem('agora_workspace', 'w')

    clearPersistedSession()

    expect(localStorage.getItem(SUPABASE_STORAGE_KEY)).toBeNull()
    expect(localStorage.getItem(`${SUPABASE_STORAGE_KEY}-code-verifier`)).toBeNull()
    expect(localStorage.getItem(`${SUPABASE_STORAGE_KEY}-user`)).toBeNull()
    expect(localStorage.getItem('agora_workspace')).toBe('w')
  })

  it('übernimmt eine Session unter dem alten Standardschlüssel und entfernt ihn', () => {
    localStorage.setItem('sb-proj-auth-token', '{"access_token":"alt"}')
    localStorage.setItem('sb-proj-auth-token-code-verifier', 'v')

    initSupabaseClient({
      auth_backend: 'hybrid',
      jwt_enabled: true,
      supabase_url: 'https://proj.supabase.example',
      supabase_anon_key: 'k',
      realtime_enabled: false,
    })

    expect(localStorage.getItem(SUPABASE_STORAGE_KEY)).toBe('{"access_token":"alt"}')
    expect(localStorage.getItem(`${SUPABASE_STORAGE_KEY}-code-verifier`)).toBe('v')
    expect(localStorage.getItem('sb-proj-auth-token')).toBeNull()
    expect(localStorage.getItem('sb-proj-auth-token-code-verifier')).toBeNull()
  })

  it('überschreibt eine Session unter dem neuen Schlüssel nicht', () => {
    localStorage.setItem(SUPABASE_STORAGE_KEY, '{"access_token":"neu"}')
    localStorage.setItem('sb-proj-auth-token', '{"access_token":"alt"}')

    initSupabaseClient({
      auth_backend: 'hybrid',
      jwt_enabled: true,
      supabase_url: 'https://proj.supabase.example',
      supabase_anon_key: 'k',
      realtime_enabled: false,
    })

    expect(localStorage.getItem(SUPABASE_STORAGE_KEY)).toBe('{"access_token":"neu"}')
    expect(localStorage.getItem('sb-proj-auth-token')).toBeNull()
  })
})
