import { describe, it, expect } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useOperatorAccess } from '../useOperatorAccess'
import { useAuthStore } from '../../store/auth'

describe('useOperatorAccess (#1617)', () => {
  it('fällt ohne aktives Pinia auf Zugang zurück', async () => {
    const pinia = await import('pinia')
    // Kein aktives Pinia simulieren: getActivePinia liefert undefined.
    setActivePinia(undefined as unknown as ReturnType<typeof pinia.createPinia>)
    expect(useOperatorAccess().value).toBe(true)
  })

  it('verweigert den Zugang bei Supabase-Session', () => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.config = { auth_backend: 'hybrid', jwt_enabled: true, supabase_url: 'https://s.test', supabase_anon_key: 'k' }
    const access = useOperatorAccess()
    expect(access.value).toBe(true)

    auth.session = { access_token: 'x' } as never

    expect(access.value).toBe(false)
  })
})
