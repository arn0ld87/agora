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
  demoPreview: false,
  sessionWithoutWorkspace: false,
  passwordRecovery: false,
  ensureInit: vi.fn(async () => {}),
}))
vi.mock('../../store/auth', () => ({ useAuthStore: () => fakeAuth }))
vi.mock('../onboardingGuard', () => ({ onboardingGuard: vi.fn(async () => true) }))

const VIEW_STUB = vi.hoisted(() => ({ default: { name: 'ViewStub', render: () => null } }))
// Etappe 2 (#1797): /dashboard und /ablage leiten auf die Bibliothek um; die
// Start-Position der Tests ist /library/graphs, damit eine Weiterleitung nie auf
// die aktuelle Position fuehrt (vue-router wuerde sie als Duplikat verwerfen und
// den Guard auslassen).
vi.mock('../../views/library/LibraryRunsView.vue', () => VIEW_STUB)
vi.mock('../../views/library/LibraryGraphsView.vue', () => VIEW_STUB)
vi.mock('../../views/shell/ShelfView.vue', () => VIEW_STUB)
vi.mock('../../views/NotFoundView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/SettingsApiKeysView.vue', () => VIEW_STUB)
// /settings/general zeigt seit Etappe 3 (#1799) das Einstellungsfenster.
vi.mock('../../components/settings-window/SettingsWindow.vue', () => VIEW_STUB)
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
  fakeAuth.demoPreview = false
  fakeAuth.sessionWithoutWorkspace = false
  fakeAuth.passwordRecovery = false
  fakeAuth.ensureInit.mockClear()
  vi.mocked(getAgoraToken).mockReturnValue('')
  await go('/library/graphs')
})

describe('Legacy-Modus (JWT aus)', () => {
  it('lässt normale Routen ohne Anmeldung durch', async () => {
    await go('/ablage/bericht/r1')
    expect(router.currentRoute.value.name).toBe('ShelfObject')
  })

  it('leitet requiresAuth-Routen ohne Token wie bisher auf die Startseite (Bibliothek)', async () => {
    await go('/settings/providers')
    expect(router.currentRoute.value.name).toBe('LibraryRuns')
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
    await go('/ablage/bericht/r1')
    expect(fakeAuth.ensureInit).toHaveBeenCalled()
  })

  it('leitet ohne Session auf Login mit next', async () => {
    await go('/ablage/bericht/r1?x=1')
    expect(router.currentRoute.value.name).toBe('Login')
    expect(router.currentRoute.value.query.next).toBe('/ablage/bericht/r1?x=1')
  })

  it('lässt öffentliche Auth-Routen ohne Session durch', async () => {
    await go('/auth/register')
    expect(router.currentRoute.value.name).toBe('Register')
  })

  it('schickt angemeldete Nutzer vom Login zu next', async () => {
    fakeAuth.isAuthenticated = true
    await go('/auth/login?next=/dashboard')
    expect(router.currentRoute.value.name).toBe('LibraryRuns')
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

  it.each(['/settings/general', '/settings/access', '/onboarding'])(
    'laesst Besucher mit Session auf %s (Demo-Vorschau statt Redirect)',
    async (path) => {
      // Im echten Store impliziert operatorAccess=false immer eine Session
      // und damit demoPreview=true — der Mock bildet beides nach.
      fakeAuth.operatorAccess = false
      fakeAuth.demoPreview = true
      await go(path)
      expect(router.currentRoute.value.path).toBe(path)
    },
  )

  it('leitet Betreiber-Routen um, wenn weder operatorAccess noch demoPreview vorliegen (Verteidigungslinie)', async () => {
    // Dieser Zustand ist im echten Store nicht erreichbar (operatorAccess=false
    // impliziert demoPreview=true), der Guard bleibt aber defensiv korrekt.
    fakeAuth.operatorAccess = false
    fakeAuth.demoPreview = false
    await go('/settings/general')
    expect(router.currentRoute.value.name).toBe('LibraryRuns')
  })

  it('lässt Betreiber (Master-Token in hybrid) auf die Einstellungen', async () => {
    fakeAuth.operatorAccess = true
    vi.mocked(getAgoraToken).mockReturnValue('master')
    await go('/settings/general')
    expect(router.currentRoute.value.name).toBe('SettingsGeneral')
  })
})

describe('Session ohne Workspace im JWT-Modus (Recovery)', () => {
  beforeEach(() => {
    fakeAuth.jwtEnabled = true
    fakeAuth.isAuthenticated = true
    fakeAuth.operatorAccess = false
    fakeAuth.sessionWithoutWorkspace = true
    fakeAuth.passwordRecovery = true
  })

  it('lässt den Passwort-Reset zu', async () => {
    await go('/auth/reset')
    expect(router.currentRoute.value.name).toBe('PasswordReset')
  })

  it('leitet geschützte Routen auf den Reset zurück', async () => {
    await go('/ablage/bericht/r1')
    expect(router.currentRoute.value.name).toBe('PasswordReset')
  })

  it('schickt den Login-Link nicht in die App', async () => {
    await go('/auth/login?next=/ablage')
    expect(router.currentRoute.value.name).toBe('Login')
  })

  it.each(['/auth/register', '/auth/confirm'])('leitet %s auf den Reset zurück', async (path) => {
    await go(path)
    expect(router.currentRoute.value.name).toBe('PasswordReset')
  })

  it('schickt ohne Recovery auch öffentliche Routen auf den Login', async () => {
    fakeAuth.passwordRecovery = false
    await go('/auth/register')
    expect(router.currentRoute.value.name).toBe('Login')
  })

  it('leitet ohne Recovery auf den Login', async () => {
    fakeAuth.passwordRecovery = false
    await go('/ablage/bericht/r1')
    expect(router.currentRoute.value.name).toBe('Login')
  })
})
