/**
 * Log-Drawer für Supabase-Nutzer gesperrt (#1617): Logs sind operator_only.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '../../store/auth'
import { useLogDrawer } from '../useLogDrawer'

function hotkey(): KeyboardEvent {
  return new KeyboardEvent('keydown', { key: 'L', ctrlKey: true, shiftKey: true, cancelable: true })
}

describe('useLogDrawer mit Supabase-Session', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useLogDrawer().close()
  })

  it('bleibt für Betreiber verfügbar', () => {
    const drawer = useLogDrawer()

    drawer.open()

    expect(drawer.available.value).toBe(true)
    expect(drawer.visible.value).toBe(true)
  })

  it('sperrt Knopf, Hotkey und Drawer für Supabase-Nutzer', () => {
    const auth = useAuthStore()
    auth.config = { auth_backend: 'hybrid', jwt_enabled: true, supabase_url: 'https://s.test', supabase_anon_key: 'k', realtime_enabled: false }
    auth.session = { access_token: 'x' } as never
    const drawer = useLogDrawer()

    drawer.open()
    const event = hotkey()
    drawer.handleHotkey(event)

    expect(drawer.available.value).toBe(false)
    expect(drawer.visible.value).toBe(false)
    expect(event.defaultPrevented).toBe(false)
  })
})
