/**
 * Router-Spec: testet Routen-Resolution, Redirects, Catch-all NotFound und Auth-Guard.
 *
 * Strategie: vue-router's createWebHistory wird durch createMemoryHistory ersetzt,
 * damit der Production-Router direkt importiert und mit router.push() getestet
 * werden kann — ohne den Router lokal neu zu bauen (Vermeidung von resolve-Hängern
 * bei dynamic-import-Components).
 */
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    createWebHistory: () => actual.createMemoryHistory(),
  }
})

vi.mock('../../api/index', () => ({
  getAgoraToken: vi.fn(() => ''),
  default: {
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}))

// i18n liest beim Module-Load localStorage → in jsdom verfügbar, aber wir
// vermeiden den Side-Effect, damit der Test deterministisch bleibt, auch wenn
// Components transitive i18n importieren.
vi.mock('../../i18n/index', () => ({
  default: { global: { t: (k: string) => k, locale: { value: 'de' } } },
  setLocale: vi.fn(),
}))

// Die Produktion-Routen referenzieren ihre Views als lazy `() => import(...)`.
// vue-router löst diese Async-Components bei jedem `router.push()` auf (nicht
// erst beim Render). Isoliert kostet das ~0,5 s pro erstem Routen-Besuch
// (View-Transform); im parallelen Full-Suite-Lauf ballt sich die Transform-
// Last auf >10 s pro Navigation → der beforeAll-Hook überschreitet das
// Default-hookTimeout (10 s) und der ganze File flakt. Dieser Spec testet
// ausschließlich Routen-Resolution/Redirects/Guards/meta-Flags — es wird keine
// Komponente gerendert. Also stubben wir die besuchten Views auf einen Noop,
// damit `push()` deterministisch ~1 ms bleibt. Assertions bleiben unberührt.
const VIEW_STUB = vi.hoisted(() => ({
  default: { name: 'ViewStub', render: () => null },
}))
vi.mock('../../views/v4/DashboardView.vue', () => VIEW_STUB)
vi.mock('../../views/v4/RunsAppShellView.vue', () => VIEW_STUB)
vi.mock('../../views/v4/CompareView.vue', () => VIEW_STUB)
vi.mock('../../views/v4/steps/StepGraphBuildView.vue', () => VIEW_STUB)
vi.mock('../../views/v4/steps/StepEnvSetupView.vue', () => VIEW_STUB)
vi.mock('../../views/v4/steps/StepSimulationView.vue', () => VIEW_STUB)
vi.mock('../../views/v4/steps/StepReportView.vue', () => VIEW_STUB)
vi.mock('../../views/v4/steps/StepInteractionView.vue', () => VIEW_STUB)
vi.mock('../../views/Home.vue', () => VIEW_STUB)
vi.mock('../../views/NotFoundView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/SettingsGeneralView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/SettingsIntegrationsView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/SettingsApiKeysView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/SettingsAuditLogsView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/LlmRoutingView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/LlmProvidersView.vue', () => VIEW_STUB)

import router from '../index'
import { getAgoraToken } from '../../api/index'

async function pushAndSettle(path: string): Promise<void> {
  await router.push(path)
  await flushPromises()
}

beforeAll(async () => {
  vi.mocked(getAgoraToken).mockReturnValue('tkn')
  await router.push('/')
  await router.isReady()
})

describe('Router – Routen-Resolution', () => {
  beforeEach(() => {
    vi.mocked(getAgoraToken).mockReturnValue('tkn')
  })

  it.each([
    ['/dashboard', 'Dashboard'],
    ['/runs', 'Runs'],
    ['/settings/general', 'SettingsGeneral'],
    ['/settings/integrations', 'SettingsIntegrations'],
    ['/home', 'Home'],
  ])('löst %s → %s auf', async (path, name) => {
    await pushAndSettle(path)
    expect(router.currentRoute.value.name).toBe(name)
  })

  it('löst /v4/compare/:simulationId mit param auf', async () => {
    await pushAndSettle('/v4/compare/sim_abc')
    expect(router.currentRoute.value.name).toBe('CompareV4')
    expect(router.currentRoute.value.params.simulationId).toBe('sim_abc')
  })
})

describe('Router – Redirects', () => {
  beforeEach(() => {
    vi.mocked(getAgoraToken).mockReturnValue('tkn')
  })

  it.each([
    ['/', 'Dashboard'],
    ['/v4/dashboard', 'Dashboard'],
    ['/settings', 'SettingsGeneral'],
    ['/settings-classic', 'SettingsGeneral'],
  ])('%s → %s', async (from, to) => {
    await pushAndSettle(from)
    expect(router.currentRoute.value.name).toBe(to)
  })

  it('hält /settings-classic nur als expliziten benannten Redirect', () => {
    const classicRoute = router.getRoutes().find((route) => route.path === '/settings-classic')

    expect(classicRoute?.redirect).toEqual({ name: 'SettingsGeneral' })
    expect(classicRoute?.components).toBeUndefined()
  })

  it.each([
    ['/process/project_42', 'StepGraphBuild', { projectId: 'project_42' }],
    ['/simulation/simulation_42', 'StepEnvSetup', { projectId: 'simulation_42' }],
    ['/simulation/simulation_42/start', 'StepSimulation', { simulationId: 'simulation_42' }],
    ['/report/report_42', 'StepReport', { reportId: 'report_42' }],
    ['/interaction/report_42', 'StepInteraction', { reportId: 'report_42' }],
  ])('leitet %s auf %s mit dokumentiertem Parameter-Mapping weiter', async (from, to, params) => {
    await pushAndSettle(from)

    expect(router.currentRoute.value.name).toBe(to)
    expect(router.currentRoute.value.params).toMatchObject(params)
  })
})

describe('Router – Catch-all NotFound', () => {
  beforeEach(() => {
    vi.mocked(getAgoraToken).mockReturnValue('tkn')
  })

  it.each(['/foo/bar/baz', '/komplett/unbekannt/pfad'])(
    '%s → NotFound',
    async (path) => {
      await pushAndSettle(path)
      expect(router.currentRoute.value.name).toBe('NotFound')
    },
  )
})

describe('Router – Auth-Guard', () => {
  beforeEach(() => {
    vi.mocked(getAgoraToken).mockReset()
  })

  it('ohne Token: /settings/api-keys → Dashboard mit authRequired + next', async () => {
    vi.mocked(getAgoraToken).mockReturnValue('')
    await pushAndSettle('/settings/api-keys')
    const route = router.currentRoute.value
    expect(route.name).toBe('Dashboard')
    expect(route.query.authRequired).toBe('1')
    expect(route.query.next).toBe('/settings/api-keys')
  })

  it('mit Token: /settings/api-keys → SettingsApiKeys', async () => {
    vi.mocked(getAgoraToken).mockReturnValue('tkn')
    await pushAndSettle('/settings/api-keys')
    expect(router.currentRoute.value.name).toBe('SettingsApiKeys')
  })

  it.each([
    '/settings/audit-logs',
    '/settings/llm-routing',
    '/settings/llm-providers',
  ])('ohne Token: %s → Dashboard', async (path) => {
    vi.mocked(getAgoraToken).mockReturnValue('')
    await pushAndSettle(path)
    expect(router.currentRoute.value.name).toBe('Dashboard')
  })

  it('öffentliche Settings-Route bleibt ohne Token erreichbar', async () => {
    vi.mocked(getAgoraToken).mockReturnValue('')
    await pushAndSettle('/settings/general')
    expect(router.currentRoute.value.name).toBe('SettingsGeneral')
    expect(router.currentRoute.value.meta.requiresAuth).toBeFalsy()
  })
})

describe('Router – meta.requiresAuth Flag-Integrität', () => {
  it('alle 4 protected Settings-Routen tragen meta.requiresAuth=true', () => {
    const protectedPaths = [
      '/settings/api-keys',
      '/settings/audit-logs',
      '/settings/llm-routing',
      '/settings/llm-providers',
    ]
    for (const path of protectedPaths) {
      const resolved = router.resolve(path)
      expect(resolved.meta.requiresAuth, `${path} soll requiresAuth=true`).toBe(true)
    }
  })

  it('öffentliche Settings-Routen tragen KEIN requiresAuth', () => {
    const publicPaths = [
      '/settings/general',
      '/settings/integrations',
      '/settings/users-teams',
    ]
    for (const path of publicPaths) {
      const resolved = router.resolve(path)
      expect(resolved.meta.requiresAuth, `${path} soll KEIN requiresAuth`).toBeFalsy()
    }
  })
})
