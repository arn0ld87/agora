/**
 * Auth-Guard (#1617): JWT-Modus leitet ohne Session auf Login, Legacy bleibt.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return { ...actual, createWebHistory: () => actual.createMemoryHistory() }
})

vi.mock('../../api/index', () => ({
  getAgoraToken: vi.fn(() => ''),
  default: { interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } } },
}))

vi.mock('../../i18n/index', () => ({
  default: { global: { t: (k: string) => k, locale: { value: 'de' } } },
  setLocale: vi.fn(),
}))

const fakeAuth = vi.hoisted(() => ({
  jwtEnabled: false,
  isAuthenticated: false,
  operatorAccess: true,
  ensureInit: vi.fn(async () => {}),
}))
vi.mock('../../store/auth', () => ({ useAuthStore: () => fakeAuth }))
vi.mock('../onboardingGuard', () => ({ onboardingGuard: vi.fn(async () => true) }))

const VIEW_STUB = vi.hoisted(() => ({ default: { name: 'ViewStub', render: () => null } }))
vi.mock('../../views/v4/DashboardView.vue', () => VIEW_STUB)
vi.mock('../../views/shell/ShelfView.vue', () => VIEW_STUB)
vi.mock('../../views/NotFoundView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/SettingsApiKeysView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/SettingsGeneralView.vue', () => VIEW_STUB)
vi.mock('../../views/onboarding/OnboardingView.vue', () => VIEW_STUB)
vi.mock('../../views/auth/LoginView.vue', () => VIEW_STUB)
vi.mock('../../views/auth/RegisterView.vue', () => VIEW_STUB)
vi.mock('../../views/auth/PasswordResetView.vue', () => VIEW_STUB)
vi.mock('../../views/auth/EmailConfirmView.vue', () => VIEW_STUB)

import router from '../index'
import { getAgoraToken } from '../../api/index'

async function go(path: string): Promise<void> {
  await router.push(path).catch(() => {})
  await flushPromises()
}

beforeEach(async () => {
  fakeAuth.jwtEnabled = false
  fakeAuth.isAuthenticated = false
  fakeAuth.operatorAccess = true
  fakeAuth.ensureInit.mockClear()
  vi.mocked(getAgoraToken).mockReturnValue('')
  await go('/dashboard')
})

describe('Legacy-Modus (JWT aus)', () => {
  it('lässt normale Routen ohne Anmeldung durch', async () => {
    await go('/ablage')
    expect(router.currentRoute.value.name).toBe('Shelf')
  })

  it('leitet requiresAuth-Routen ohne Token wie bisher auf das Dashboard', async () => {
    await go('/settings/api-keys')
    expect(router.currentRoute.value.name).toBe('Dashboard')
    expect(router.currentRoute.value.query.authRequired).toBe('1')
  })

  it('schickt Auth-Routen auf die Startseite', async () => {
    await go('/auth/register')
    expect(router.currentRoute.value.path).not.toBe('/auth/register')
  })
})

describe('JWT-Modus', () => {
  beforeEach(() => {
    fakeAuth.jwtEnabled = true
  })

  it('wartet auf den Auth-Start', async () => {
    await go('/ablage')
    expect(fakeAuth.ensureInit).toHaveBeenCalled()
  })

  it('leitet ohne Session auf Login mit next', async () => {
    await go('/ablage?x=1')
    expect(router.currentRoute.value.name).toBe('Login')
    expect(router.currentRoute.value.query.next).toBe('/ablage?x=1')
  })

  it('lässt öffentliche Auth-Routen ohne Session durch', async () => {
    await go('/auth/register')
    expect(router.currentRoute.value.name).toBe('Register')
  })

  it('schickt angemeldete Nutzer vom Login zu next', async () => {
    fakeAuth.isAuthenticated = true
    await go('/auth/login?next=/dashboard')
    expect(router.currentRoute.value.name).toBe('Dashboard')
  })

  it('akzeptiert kein externes next', async () => {
    fakeAuth.isAuthenticated = true
    await go('/auth/login?next=//evil.example/x')
    expect(router.currentRoute.value.path).not.toContain('evil')
    expect(router.currentRoute.value.name).not.toBe('Login')
  })
})

describe('Betreiber-Routen im JWT-Modus', () => {
  beforeEach(() => {
    fakeAuth.jwtEnabled = true
    fakeAuth.isAuthenticated = true
  })

  it.each(['/settings/general', '/settings/api-keys', '/onboarding'])(
    'hält Supabase-Nutzer von %s fern',
    async (path) => {
      fakeAuth.operatorAccess = false
      await go(path)
      expect(router.currentRoute.value.path).not.toBe(path)
      expect(router.currentRoute.value.name).toBe('Shelf')
    },
  )

  it('lässt Betreiber (Master-Token in hybrid) auf die Einstellungen', async () => {
    fakeAuth.operatorAccess = true
    vi.mocked(getAgoraToken).mockReturnValue('master')
    await go('/settings/general')
    expect(router.currentRoute.value.name).toBe('SettingsGeneral')
  })
})
