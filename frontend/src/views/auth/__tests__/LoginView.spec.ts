/**
 * LoginView (#1617): Anmeldung, sichere Weiterleitung, Fehler als role=alert.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const nav = vi.hoisted(() => ({ replace: vi.fn(async () => {}), query: {} as Record<string, unknown> }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ replace: nav.replace }),
  useRoute: () => ({ query: nav.query }),
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))

const auth = vi.hoisted(() => ({ signIn: vi.fn(), signInWithToken: vi.fn(), jwtEnabled: true }))
vi.mock('../../../store/auth', () => ({ useAuthStore: () => auth }))

import LoginView from '../LoginView.vue'

function render() {
  return mount(LoginView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
}

async function fillAndSubmit(wrapper: ReturnType<typeof render>) {
  await wrapper.find('#login-email').setValue('alice@example.test')
  await wrapper.find('#login-password').setValue('ein-langes-passwort')
  await wrapper.find('form').trigger('submit.prevent')
}

beforeEach(() => {
  nav.replace.mockClear()
  nav.query = {}
  auth.signIn.mockReset()
  auth.signInWithToken.mockReset()
  auth.jwtEnabled = true
})

describe('LoginView', () => {
  it('meldet an und leitet auf next weiter', async () => {
    auth.signIn.mockResolvedValue(undefined)
    nav.query = { next: '/runs/abc' }
    const wrapper = render()

    await fillAndSubmit(wrapper)
    await flushPromises()

    expect(auth.signIn).toHaveBeenCalledWith('alice@example.test', 'ein-langes-passwort')
    expect(nav.replace).toHaveBeenCalledWith('/runs/abc')
  })

  it('ignoriert ein externes next', async () => {
    auth.signIn.mockResolvedValue(undefined)
    nav.query = { next: 'https://evil.example' }
    const wrapper = render()

    await fillAndSubmit(wrapper)
    await flushPromises()

    expect(nav.replace).toHaveBeenCalledWith('/')
  })

  it('zeigt einen allgemeinen Fehler als Alert', async () => {
    auth.signIn.mockRejectedValue(new Error('Invalid login credentials'))
    const wrapper = render()

    await fillAndSubmit(wrapper)
    await flushPromises()

    const alert = wrapper.find('[role="alert"]')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toBe('auth.login.errorGeneric')
    expect(alert.text()).not.toContain('Invalid')
    expect(nav.replace).not.toHaveBeenCalled()
  })

  it('sperrt den Button während der Anmeldung', async () => {
    let finish: () => void = () => {}
    auth.signIn.mockReturnValue(new Promise<void>((resolve) => { finish = resolve }))
    const wrapper = render()

    await fillAndSubmit(wrapper)
    const button = wrapper.find('button[type="submit"]')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.attributes('aria-busy')).toBe('true')

    finish()
    await flushPromises()
    expect(wrapper.find('button[type="submit"]').attributes('disabled')).toBeUndefined()
  })
})

describe('LoginView ohne JWT (Betreiber-Token)', () => {
  beforeEach(() => {
    auth.jwtEnabled = false
  })

  it('zeigt das Token-Feld und kein E-Mail-Feld', () => {
    const wrapper = render()
    const input = wrapper.find('#login-token')
    expect(input.exists()).toBe(true)
    expect(input.attributes('type')).toBe('password')
    expect(wrapper.find('#login-email').exists()).toBe(false)
    expect(wrapper.find('#login-password').exists()).toBe(false)
    expect(wrapper.find('.auth-links').exists()).toBe(false)
  })

  it('übergibt das getrimmte Token und leitet auf next weiter', async () => {
    auth.signInWithToken.mockResolvedValue(undefined)
    nav.query = { next: '/runs/abc' }
    const wrapper = render()

    await wrapper.find('#login-token').setValue('  test-token  ')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(auth.signInWithToken).toHaveBeenCalledWith('test-token')
    expect(nav.replace).toHaveBeenCalledWith('/runs/abc')
  })

  it('zeigt bei abgelehntem Token einen Alert am Feld', async () => {
    auth.signInWithToken.mockRejectedValue(new Error('token_rejected'))
    const wrapper = render()

    await wrapper.find('#login-token').setValue('test-token')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.find('[role="alert"]').text()).toBe('auth.login.tokenInvalid')
    expect(wrapper.find('#login-token').attributes('aria-invalid')).toBe('true')
    expect(nav.replace).not.toHaveBeenCalled()
  })
})
