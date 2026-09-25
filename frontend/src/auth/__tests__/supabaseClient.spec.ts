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
})
