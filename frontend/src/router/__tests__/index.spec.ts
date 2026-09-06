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
vi.mock('../../views/NotFoundView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/SettingsGeneralView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/SettingsIntegrationsView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/SettingsApiKeysView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/SettingsAuditLogsView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/LlmRoutingView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/LlmProvidersView.vue', () => VIEW_STUB)
// Issue #838 — Lücken aus der Routen-Konsolidierung (ADR-0010) schließen.
vi.mock('../../views/v4/RunDetailAppShellView.vue', () => VIEW_STUB)
vi.mock('../../views/onboarding/OnboardingView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/SettingsProfileView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/EmbeddingConfigurationsView.vue', () => VIEW_STUB)
vi.mock('../../views/v4/steps/StepSimulationFeedView.vue', () => VIEW_STUB)
vi.mock('../../views/v4/HistoryView.vue', () => VIEW_STUB)

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
    ['/onboarding', 'Onboarding'],
    ['/settings/profile', 'SettingsProfile'],
    ['/settings/audit-logs', 'SettingsAuditLogs'],
    ['/settings/llm-routing', 'SettingsLlmRouting'],
    ['/settings/llm-providers', 'SettingsLlmProviders'],
    ['/settings/embedding', 'SettingsEmbedding'],
    ['/v4/history', 'HistoryV4'],
  ])('löst %s → %s auf', async (path, name) => {
    await pushAndSettle(path)
    expect(router.currentRoute.value.name).toBe(name)
  })

  it('löst /v4/compare/:simulationId mit param auf', async () => {
    await pushAndSettle('/v4/compare/sim_abc')
    expect(router.currentRoute.value.name).toBe('CompareV4')
    expect(router.currentRoute.value.params.simulationId).toBe('sim_abc')
  })

  it('löst /runs/:id mit param auf', async () => {
    await pushAndSettle('/runs/run_abc')
    expect(router.currentRoute.value.name).toBe('RunDetail')
    expect(router.currentRoute.value.params.id).toBe('run_abc')
  })

  it('löst /v4/graph-build/:projectId mit param auf', async () => {
    await pushAndSettle('/v4/graph-build/project_abc')
    expect(router.currentRoute.value.name).toBe('StepGraphBuild')
    expect(router.currentRoute.value.params.projectId).toBe('project_abc')
  })

  it('löst /v4/env-setup/:projectId mit param auf', async () => {
    await pushAndSettle('/v4/env-setup/project_abc')
    expect(router.currentRoute.value.name).toBe('StepEnvSetup')
    expect(router.currentRoute.value.params.projectId).toBe('project_abc')
  })

  it('löst /v4/simulation/:simulationId mit param auf', async () => {
    await pushAndSettle('/v4/simulation/sim_abc')
    expect(router.currentRoute.value.name).toBe('StepSimulation')
    expect(router.currentRoute.value.params.simulationId).toBe('sim_abc')
  })

  it('löst /v4/simulation/:simulationId/feed mit param auf', async () => {
    await pushAndSettle('/v4/simulation/sim_abc/feed')
    expect(router.currentRoute.value.name).toBe('StepSimulationFeed')
    expect(router.currentRoute.value.params.simulationId).toBe('sim_abc')
  })

  it('löst /v4/report/:reportId mit param auf', async () => {
    await pushAndSettle('/v4/report/report_abc')
    expect(router.currentRoute.value.name).toBe('StepReport')
    expect(router.currentRoute.value.params.reportId).toBe('report_abc')
  })

  it('löst /v4/interaction/:reportId mit param auf', async () => {
    await pushAndSettle('/v4/interaction/report_abc')
    expect(router.currentRoute.value.name).toBe('StepInteraction')
    expect(router.currentRoute.value.params.reportId).toBe('report_abc')
  })
})

describe('Router – Redirects', () => {
  beforeEach(() => {
    vi.mocked(getAgoraToken).mockReturnValue('tkn')
  })

  it.each([
    // Die Wurzel fuehrt jetzt in die Ablage: der Shell-Standard ist
    // seit B3/B4 „dossier“. /home und /v4/dashboard bleiben auf dem
    // Dashboard, solange die klassische Huelle existiert.
    ['/', 'Shelf'],
    ['/v4/dashboard', 'Dashboard'],
    ['/home', 'Dashboard'],
    ['/settings', 'SettingsGeneral'],
    ['/settings-classic', 'SettingsGeneral'],
    ['/settings/users-teams', 'SettingsProfile'],
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

  // Issue #838c: Query-Erhalt bei funktionalen Redirects (redirect: (to) => ({...})).
  // Ist-Zustand, kein Wunschverhalten: die Redirect-Factories in router/index.ts
  // geben nur { name, params } zurück, ohne query explizit weiterzureichen.
  // Empirisch (dieser Test) behält vue-router 5 den Query-String des
  // ursprünglichen `to` dennoch bei — der Original-Location-Query wird beim
  // Redirect-Resolve gemergt, nicht durch das Redirect-Objekt überschrieben.
  // Dieser Test pinnt dieses tatsächliche, positive Verhalten.
  it('funktionaler Redirect /report/:reportId behält die Query (Ist-Zustand, dokumentiert)', async () => {
    await pushAndSettle('/report/report_42?tab=evidence')

    expect(router.currentRoute.value.name).toBe('StepReport')
    expect(router.currentRoute.value.query.tab).toBe('evidence')
  })
})

describe('Router – Struktur-Integrität', () => {
  it('kein Pfad ist doppelt registriert', () => {
    const paths = router.getRoutes().map((route) => route.path)
    const duplicates = paths.filter((path, index) => paths.indexOf(path) !== index)
    expect(duplicates, `doppelte Pfade: ${duplicates.join(', ')}`).toEqual([])
  })

  it('kein Route-Name ist doppelt vergeben', () => {
    const names = router
      .getRoutes()
      .map((route) => route.name)
      .filter((name): name is string => name != null)
    const duplicates = names.filter((name, index) => names.indexOf(name) !== index)
    expect(duplicates, `doppelte Namen: ${duplicates.join(', ')}`).toEqual([])
  })

  it('jeder Eintrag hat entweder redirect ODER Komponente, nie beides', () => {
    for (const route of router.getRoutes()) {
      const hasRedirect = route.redirect !== undefined
      const hasComponent = Object.values(route.components ?? {}).some((c) => c != null)
      expect(
        hasRedirect && hasComponent,
        `Route ${String(route.name)} (${route.path}) hat sowohl redirect als auch Komponente`,
      ).toBe(false)
      expect(
        hasRedirect || hasComponent,
        `Route ${String(route.name)} (${route.path}) hat weder redirect noch Komponente`,
      ).toBe(true)
    }
  })

  // Issue #838e: robuste Form gegen "keine toten Legacy-Referenzen" — der Test
  // läuft gegen den tatsächlichen Router-Code (jede nicht-redirect Route muss
  // eine auflösbare Komponente liefern), nicht gegen eine handgepflegte
  // Stringliste gelöschter Views (#831/#832/#833/#835: MainView.vue,
  // SimulationView.vue, SimulationRunView.vue, ReportView.vue,
  // InteractionView.vue, SettingsView.vue, SettingsUsersTeamsView.vue,
  // AppShellDemoView.vue, Agora2026View.vue, ActiveModelBadge.vue,
  // Workspace*-Familie — alle laut Filesystem-Check nicht mehr vorhanden).
  it('jede nicht-redirect Route liefert eine auflösbare Komponente (keine toten Legacy-Referenzen)', async () => {
    for (const route of router.getRoutes()) {
      if (route.redirect !== undefined) continue
      const componentEntry = route.components?.default
      expect(
        componentEntry,
        `Route ${String(route.name)} (${route.path}) hat keine components.default`,
      ).toBeTruthy()
      // Lazy-Component-Loader auflösen — ein toter Import (gelöschte Datei)
      // lässt den dynamic import() zur Laufzeit fehlschlagen.
      if (typeof componentEntry === 'function') {
        await expect(
          (componentEntry as () => Promise<unknown>)(),
          `Route ${String(route.name)} (${route.path}) referenziert eine nicht auflösbare Komponente`,
        ).resolves.toBeTruthy()
      }
    }
  })

  // Issue #838f: Vollständigkeitstest gegen Drift — explizit gepflegte
  // SOLL-Liste der produktiven (nicht-redirect) Route-Namen aus der Ist-Matrix
  // im Auftrag. Fällt auf jede künftig hinzugefügte oder entfernte Route.
  it('produktive Route-Namen entsprechen exakt der gepflegten SOLL-Liste', () => {
    const SOLL_PRODUKTIVE_ROUTEN = [
      'Dashboard',
      'Runs',
      'RunDetail',
      'Onboarding',
      'SettingsGeneral',
      'SettingsIntegrations',
      'SettingsProfile',
      'SettingsApiKeys',
      'SettingsAuditLogs',
      'SettingsLlmRouting',
      'SettingsLlmProviders',
      'SettingsEmbedding',
      'StepGraphBuild',
      'StepEnvSetup',
      'StepSimulation',
      'StepSimulationFeed',
      // Redesign PR 7 (Audit §5 "Simulation live"): Vollbild-Instrument.
      'SimulationLive',
      'StepReport',
      'StepInteraction',
      'CompareV4',
      'HistoryV4',
      // Block B3: die neue Huelle. Beide zeigen auf ShelfView; der
      // Flag entscheidet nur, wohin '/' umleitet.
      'Shelf',
      'ShelfObject',
      'NotFound',
    ].sort()

    const istProduktiveRouten = router
      .getRoutes()
      .filter((route) => route.redirect === undefined)
      .map((route) => String(route.name))
      .sort()

    expect(istProduktiveRouten).toEqual(SOLL_PRODUKTIVE_ROUTEN)
  })
})

describe('Router – Deep-Links (Legacy-Pfade)', () => {
  beforeEach(() => {
    vi.mocked(getAgoraToken).mockReturnValue('tkn')
  })

  it.each([
    ['/process/project_42', 'StepGraphBuild'],
    ['/simulation/simulation_42', 'StepEnvSetup'],
    ['/simulation/simulation_42/start', 'StepSimulation'],
    ['/report/report_42', 'StepReport'],
    ['/interaction/report_42', 'StepInteraction'],
  ])('Legacy-Deep-Link %s landet deterministisch auf %s, KEIN NotFound', async (path, expected) => {
    await pushAndSettle(path)
    expect(router.currentRoute.value.name).toBe(expected)
    expect(router.currentRoute.value.name).not.toBe('NotFound')
  })

  it.each(['/settings-classic', '/settings/users-teams'])(
    '%s landet nicht auf NotFound',
    async (path) => {
      await pushAndSettle(path)
      expect(router.currentRoute.value.name).not.toBe('NotFound')
    },
  )

  // Regressionstest Issue #832: /agora-2026 ist die dokumentierte 404-Ausnahme
  // (ADR-0010) — die einzige entfernte Route, die absichtlich auf NotFound fällt.
  it('/agora-2026 → NotFound (dokumentierte Ausnahme, ADR-0010 + Issue #832)', async () => {
    await pushAndSettle('/agora-2026')
    expect(router.currentRoute.value.name).toBe('NotFound')
  })

  it('ADR-0010-Seam: /simulation/:simulationId → StepEnvSetup mit Parameter-Umbenennung simulationId→projectId', async () => {
    // Ungewöhnlicher Mapping-Seam (siehe docs/decisions/0010-vue-v4-route-consolidation.md):
    // der Legacy-Pfadparameter heisst ":simulationId", landet aber unter dem
    // Namen "projectId" im Ziel-Routen-Objekt — der WERT bleibt unverändert
    // die Simulation-ID. ADR-0010 verlangt, dass dieser Seam explizit
    // benannt und mit einem eigenen Test abgesichert wird.
    await pushAndSettle('/simulation/sim_seam_check')
    expect(router.currentRoute.value.name).toBe('StepEnvSetup')
    expect(router.currentRoute.value.params.projectId).toBe('sim_seam_check')
    expect(router.currentRoute.value.params.simulationId).toBeUndefined()
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

  // Regressionstest Issue #832: /agora-2026 war eine reine Designexploration,
  // die produktiv geroutet wurde. Nach der Archivierung nach
  // docs/design-reference/agora-2026/ darf die Route keine eigene Komponente
  // mehr auflösen, sondern muss auf die Catch-all-NotFound-Route zurückfallen.
  it('/agora-2026 → NotFound (Designexploration archiviert, Issue #832)', async () => {
    await pushAndSettle('/agora-2026')
    expect(router.currentRoute.value.name).toBe('NotFound')
  })
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
