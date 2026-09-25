/**
 * PasswordResetView (#1617): nach dem Reset ohne aktivierbaren Workspace zum
 * Login mit Hinweis statt in die App ohne X-Agora-Workspace.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const nav = vi.hoisted(() => ({ replace: vi.fn(async () => {}) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ replace: nav.replace }) }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))

const auth = vi.hoisted(() => ({
  passwordRecovery: true,
  updatePassword: vi.fn(),
  requestPasswordReset: vi.fn(),
}))
vi.mock('../../../store/auth', async () => {
  class PasswordUpdatedSignInRequired extends Error {}
  return { useAuthStore: () => auth, PasswordUpdatedSignInRequired }
})

import PasswordResetView from '../PasswordResetView.vue'
import { PasswordUpdatedSignInRequired } from '../../../store/auth'

async function submitNewPassword() {
  const wrapper = mount(PasswordResetView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
  await wrapper.find('#reset-new-password').setValue('ein-neues-langes-passwort')
  await wrapper.find('#reset-confirm-password').setValue('ein-neues-langes-passwort')
  await wrapper.find('form').trigger('submit.prevent')
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  nav.replace.mockClear()
  auth.updatePassword.mockReset()
})

describe('PasswordResetView', () => {
  it('geht nach erfolgreichem Reset mit Workspace in die App', async () => {
    auth.updatePassword.mockResolvedValue(undefined)

    await submitNewPassword()

    expect(nav.replace).toHaveBeenCalledWith('/')
  })

  it('führt ohne aktivierbaren Workspace zum Login mit Hinweis', async () => {
    auth.updatePassword.mockRejectedValue(new PasswordUpdatedSignInRequired())

    const wrapper = await submitNewPassword()

    expect(nav.replace).toHaveBeenCalledWith({ name: 'Login', query: { reset: 'done' } })
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('zeigt andere Fehler als Alert', async () => {
    auth.updatePassword.mockRejectedValue(new Error('weak password'))

    const wrapper = await submitNewPassword()

    expect(nav.replace).not.toHaveBeenCalled()
    expect(wrapper.find('[role="alert"]').text()).toBe('auth.reset.errorGeneric')
  })
})
