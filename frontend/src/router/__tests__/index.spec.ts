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
import { createPinia, setActivePinia } from 'pinia'
import { useSettingsWindowStore } from '../../stores/settingsWindow'

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
vi.mock('../../views/v4/CompareView.vue', () => VIEW_STUB)
vi.mock('../../views/v4/steps/StepGraphBuildView.vue', () => VIEW_STUB)
vi.mock('../../views/v4/steps/StepEnvSetupView.vue', () => VIEW_STUB)
vi.mock('../../views/v4/steps/SimulationLayout.vue', () => VIEW_STUB)
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
vi.mock('../../views/Settings/WorkspaceProviderKeysView.vue', () => VIEW_STUB)
// Issue #838 — Lücken aus der Routen-Konsolidierung (ADR-0010) schließen.
vi.mock('../../views/onboarding/OnboardingView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/SettingsProfileView.vue', () => VIEW_STUB)
vi.mock('../../views/Settings/EmbeddingConfigurationsView.vue', () => VIEW_STUB)
vi.mock('../../views/v4/steps/StepSimulationFeedView.vue', () => VIEW_STUB)
// Slice UI-2b (#1713): Diskurs/Strang/Runden/Protokoll-Kind-Routen.
vi.mock('../../views/v4/steps/SimThreadsView.vue', () => VIEW_STUB)
vi.mock('../../views/v4/steps/SimThreadFocusView.vue', () => VIEW_STUB)
vi.mock('../../views/v4/steps/SimRoundsView.vue', () => VIEW_STUB)
vi.mock('../../views/v4/steps/SimActionsView.vue', () => VIEW_STUB)
vi.mock('../../views/shell/ShelfView.vue', () => VIEW_STUB)
// Redesign PR 8: /runs und /v4/history sind reine Redirects auf die Ablage
// (ShelfView); die abgeloesten RunsAppShellView.vue und HistoryView.vue sind
// mit PR 10 geloescht, deshalb dafür keine vi.mock()-Eintraege. /runs/:id
// bleibt eine echte Route und braucht seinen Stub weiterhin.
vi.mock('../../views/v4/RunDetailAppShellView.vue', () => VIEW_STUB)
// Etappe 2 (#1797), Ticket „Adressen": Platzhalter-Ansichten.
vi.mock('../../views/library/LibraryRunsView.vue', () => VIEW_STUB)
vi.mock('../../views/library/LibraryGraphsView.vue', () => VIEW_STUB)
vi.mock('../../views/library/NewRunView.vue', () => VIEW_STUB)
vi.mock('../../views/run/RunWorkspaceView.vue', () => VIEW_STUB)
vi.mock('../../views/run/RunOverviewView.vue', () => VIEW_STUB)
vi.mock('../../views/run/RunGraphView.vue', () => VIEW_STUB)
vi.mock('../../views/graph/GraphLibraryDetailView.vue', () => VIEW_STUB)
vi.mock('../../views/activity/ActivityJobsView.vue', () => VIEW_STUB)
vi.mock('../../views/activity/ActivityLogView.vue', () => VIEW_STUB)
// Etappe 3 (#1799), Ticket „Einstellungsfenster": das Fenster ersetzt die
// Ansichten hinter /settings/general und /settings/embedding.
vi.mock('../../components/settings-window/SettingsWindow.vue', () => VIEW_STUB)

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
    // `/dashboard` ist seit Etappe 2 eine Weiterleitung (siehe Redirects).
    ['/library/runs/new', 'NewRun'],
    ['/settings/general', 'SettingsGeneral'],
    ['/settings/integrations', 'SettingsIntegrations'],
    ['/onboarding', 'Onboarding'],
    ['/settings/profile', 'SettingsProfile'],
    ['/settings/audit-logs', 'SettingsAuditLogs'],
    ['/settings/llm-routing', 'SettingsLlmRouting'],
    ['/settings/llm-providers', 'SettingsLlmProviders'],
    ['/settings/embedding', 'SettingsEmbedding'],
  ])('löst %s → %s auf', async (path, name) => {
    await pushAndSettle(path)
    expect(router.currentRoute.value.name).toBe(name)
  })

  // Etappe 2: /v4/compare/:simulationId leitet auf /compare/:simulationId um.
  it('löst /v4/compare/:simulationId mit param auf (Weiterleitung auf Compare)', async () => {
    await pushAndSettle('/v4/compare/sim_abc')
    expect(router.currentRoute.value.name).toBe('Compare')
    expect(router.currentRoute.value.fullPath).toBe('/compare/sim_abc')
    expect(router.currentRoute.value.params.simulationId).toBe('sim_abc')
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

  // Slice UI-2b (#1713): Diskurs-, Strang-, Runden- und Protokoll-Kind-Routen.
  it('löst /v4/simulation/:simulationId/threads mit param auf', async () => {
    await pushAndSettle('/v4/simulation/sim_abc/threads')
    expect(router.currentRoute.value.name).toBe('SimThreads')
    expect(router.currentRoute.value.params.simulationId).toBe('sim_abc')
  })

  it('löst /v4/simulation/:simulationId/thread/:postId mit beiden Params auf', async () => {
    await pushAndSettle('/v4/simulation/sim_abc/thread/post_1')
    expect(router.currentRoute.value.name).toBe('SimThreadFocus')
    expect(router.currentRoute.value.params.simulationId).toBe('sim_abc')
    expect(router.currentRoute.value.params.postId).toBe('post_1')
  })

  it('löst /v4/simulation/:simulationId/rounds mit param auf', async () => {
    await pushAndSettle('/v4/simulation/sim_abc/rounds')
    expect(router.currentRoute.value.name).toBe('SimRounds')
    expect(router.currentRoute.value.params.simulationId).toBe('sim_abc')
  })

  it('löst /v4/simulation/:simulationId/actions mit param auf', async () => {
    await pushAndSettle('/v4/simulation/sim_abc/actions')
    expect(router.currentRoute.value.name).toBe('SimActions')
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
    // Etappe 2 (#1797): die Bibliothek ist die Startseite, das Dashboard
    // entfaellt (Bauplan §6.2).
    ['/', 'LibraryRuns'],
    ['/v4/dashboard', 'LibraryRuns'],
    ['/home', 'LibraryRuns'],
    ['/dashboard', 'LibraryRuns'],
    ['/settings', 'SettingsGeneral'],
    ['/settings-classic', 'SettingsGeneral'],
    ['/settings/users-teams', 'SettingsProfile'],
    // Legacy-Registry und History gehen in Bibliothek bzw. Aktivitaet auf.
    ['/runs', 'LibraryRuns'],
    ['/v4/history', 'ActivityJobs'],
  ])('%s → %s', async (from, to) => {
    await pushAndSettle(from)
    expect(router.currentRoute.value.name).toBe(to)
  })

  // Etappe 2: Tabelle 6.2, Zeilen „/ablage?filter=…“.
  it.each([
    ['/ablage', '/library/runs'],
    ['/ablage?filter=alle', '/library/runs'],
    ['/ablage?filter=lauf', '/library/runs'],
    ['/ablage?filter=bericht', '/library/runs?view=with-report'],
    ['/ablage?filter=graph', '/library/graphs'],
    // Personasaetze haben bis Etappe 7 keine eigene Ansicht.
    ['/ablage?filter=personasatz', '/library/runs'],
    ['/ablage?filter=jobs', '/activity/jobs'],
    ['/ablage?filter=unbekannt', '/library/runs'],
    ['/v4/history', '/activity/jobs'],
    ['/runs', '/library/runs'],
  ])('%s → %s (voller Pfad)', async (from, to) => {
    await pushAndSettle(from)
    expect(router.currentRoute.value.fullPath).toBe(to)
  })

  it('Ablage-Weiterleitung behält fremde Query-Schlüssel und den Hash', async () => {
    await pushAndSettle('/ablage?filter=graph&x=1#oben')
    expect(router.currentRoute.value.fullPath).toBe('/library/graphs?x=1#oben')
  })

  // Etappe 2: /ablage/lauf|graph/:objectId.
  it.each([
    ['/ablage/lauf/sim_42', 'RunOverview', { simulationId: 'sim_42' }],
    ['/ablage/graph/proj_42', 'GraphLibraryDetail', { projectId: 'proj_42' }],
    // Ein Lauf ohne Simulation fuehrt die Ablage unter der project_id bzw. run_id.
    ['/ablage/lauf/proj_42', 'GraphLibraryDetail', { projectId: 'proj_42' }],
    ['/ablage/lauf/run_42', 'ActivityJobDetail', { runId: 'run_42' }],
  ])('%s → %s', async (from, name, params) => {
    await pushAndSettle(from)
    expect(router.currentRoute.value.name).toBe(name)
    expect(router.currentRoute.value.params).toMatchObject(params)
  })

  it('/ablage/bericht und /ablage/personasatz bleiben bis Etappe 5 bzw. 7 auf der alten Ansicht', async () => {
    await pushAndSettle('/ablage/bericht/report_42')
    expect(router.currentRoute.value.name).toBe('ShelfObject')
    expect(router.currentRoute.value.params).toMatchObject({ kind: 'bericht', objectId: 'report_42' })
    await pushAndSettle('/ablage/personasatz/set_42')
    expect(router.currentRoute.value.name).toBe('ShelfObject')
    expect(router.currentRoute.value.params).toMatchObject({ kind: 'personasatz', objectId: 'set_42' })
  })

  // Abnahmekriterium Etappe 2: ein gespeicherter Link /runs/<run_id> oeffnet
  // weiterhin den Job; die Kennung bleibt unveraendert, Query und Hash auch.
  it('/runs/:id → /activity/jobs/:id mit unveränderter Kennung', async () => {
    await pushAndSettle('/runs/run_abc?tab=budget#top')
    expect(router.currentRoute.value.name).toBe('ActivityJobDetail')
    expect(router.currentRoute.value.params).toEqual({ runId: 'run_abc' })
    expect(router.currentRoute.value.fullPath).toBe('/activity/jobs/run_abc?tab=budget#top')
  })

  // Die alten Routen-Namen bleiben als Weiterleitung bestehen: kein toter Name.
  it.each([
    [{ name: 'Dashboard' }, '/library/runs'],
    [{ name: 'Runs' }, '/library/runs'],
    [{ name: 'Shelf' }, '/library/runs'],
    [{ name: 'Shelf', query: { filter: 'jobs' } }, '/activity/jobs'],
    [{ name: 'HistoryV4' }, '/activity/jobs'],
    [{ name: 'RunDetail', params: { id: 'run_abc' } }, '/activity/jobs/run_abc'],
    [{ name: 'CompareV4', params: { simulationId: 'sim_abc' } }, '/compare/sim_abc'],
    [{ name: 'ShelfObject', params: { kind: 'lauf', objectId: 'sim_abc' } }, '/simulations/sim_abc'],
  ])('alter Routen-Name %j löst auf %s', async (location, path) => {
    await router.push(location)
    await flushPromises()
    expect(router.currentRoute.value.path).toBe(path.split('?')[0])
  })

  it('die alten Routen-Namen sind Weiterleitungs-Routen', () => {
    for (const name of ['Dashboard', 'Runs', 'Shelf', 'HistoryV4', 'RunDetail', 'CompareV4']) {
      const record = router.getRoutes().find((route) => route.name === name)
      expect(record?.redirect, name).toBeDefined()
    }
  })

  // Redesign PR 10 (Legacy-Abbau): die Wurzel haengt nicht mehr an einem
  // Shell-Flag. Der Redirect ist ein statisches Ziel; eine Funktion hier
  // waere das Anzeichen, dass die Verzweigung zurueck ist.
  it('/ ist ein statischer Redirect auf die Bibliothek, ohne Shell-Flag', () => {
    const root = router.getRoutes().find((route) => route.path === '/')

    expect(root?.redirect).toEqual({ name: 'LibraryRuns' })
    expect(typeof root?.redirect).not.toBe('function')
    expect(root?.components).toBeUndefined()
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

  // Fix #1713 (Befund 6): /live war eine verwaiste Route ohne Anschluss an
  // die Tab-Navigation. Slice UI-2b: Ziel ist jetzt die Runden-Ansicht (naeher
  // am urspruenglichen Zweck als der Feed); Parameter + Query bleiben erhalten.
  it('/v4/simulation/:id/live → SimRounds, Query bleibt erhalten', async () => {
    await pushAndSettle('/v4/simulation/sim_live_1/live?projectId=project_1')

    expect(router.currentRoute.value.name).toBe('SimRounds')
    expect(router.currentRoute.value.params.simulationId).toBe('sim_live_1')
    expect(router.currentRoute.value.query.projectId).toBe('project_1')
  })
})

describe('Router – Struktur-Integrität', () => {
  it('kein Pfad ist doppelt registriert', () => {
    // Fix #1713: SimulationLayout ist ein Layout-Parent mit einer Kind-Route
    // auf leerem Pfad (StepSimulation) — vue-router registriert dafuer
    // zwei Eintraege mit demselben resolvierten Pfad (Standardmuster fuer
    // "Layout mit Default-Kind"). Nur navigierbare Blatt-Routen (ohne
    // eigene Kinder) zaehlen fuer die Duplikatspruefung; der Layout-Parent
    // selbst ist nie direkt das Navigationsziel.
    const paths = router
      .getRoutes()
      .filter((route) => !route.children || route.children.length === 0)
      .map((route) => route.path)
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
  // Eigenes Timeout: dieser Test loest die Routen-Komponenten ECHT auf, statt
  // nur den Router zu befragen. Fix #1713: `/live` ist jetzt ein reiner
  // Redirect (kein `component` mehr), `views/shell/SimulationLiveView.vue`
  // wird darum von diesem Test nicht mehr transformiert — die vormals nicht
  // gestubbte View trug hier den groessten Anteil der gemessenen Laufzeit.
  // Das erweiterte Timeout bleibt als Sicherheitsmarge fuer die verbleibenden
  // echten Transforms.
  it('jede nicht-redirect Route liefert eine auflösbare Komponente (keine toten Legacy-Referenzen)', { timeout: 30_000 }, async () => {
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
      // Etappe 2: Dashboard, RunDetail, CompareV4 und Shelf sind
      // Weiterleitungen (alte Namen bleiben, siehe Redirects-Suite) und zaehlen
      // nicht mehr als produktive Routen; neu ist NewRun (HeroNewRun-Einstieg).
      'NewRun',
      'Onboarding',
      'SettingsGeneral',
      'SettingsIntegrations',
      'SettingsProfile',
      'SettingsApiKeys',
      'SettingsAuditLogs',
      'SettingsLlmRouting',
      'SettingsLlmProviders',
      'SettingsEmbedding',
      // Etappe 3 (#1799): alle uebrigen Abschnitte des Einstellungsfensters.
      'SettingsWindow',
      'StepGraphBuild',
      'StepEnvSetup',
      'StepSimulation',
      'StepSimulationFeed',
      // Slice UI-2b (#1713): Diskurs/Strang/Runden/Protokoll-Kind-Routen.
      'SimThreads',
      'SimThreadFocus',
      'SimRounds',
      'SimActions',
      // Fix #1713 (Befund 6): /live ist jetzt ein Redirect (Ziel: SimRounds),
      // keine eigene produktive Route mehr (siehe Redirects-Suite oben).
      'StepReport',
      'StepInteraction',
      // Block B3: ShelfObject zeigt weiter auf ShelfView (Bericht und
      // Personasatz bis Etappe 5 bzw. 7); Lauf und Graph leitet beforeEnter um.
      'ShelfObject',
      // #1617: Supabase-Anmeldung, nur mit JWT erreichbar.
      'Login',
      'Register',
      'PasswordReset',
      'EmailConfirm',
      'WorkspaceProviderKeys',
      'NotFound',
      // Etappe 2 (#1797), Ticket „Adressen".
      'LibraryRuns',
      'LibraryGraphs',
      'RunWorkspace',
      'RunOverview',
      'RunGraph',
      'GraphLibraryDetail',
      'Compare',
      'ActivityJobs',
      'ActivityJobDetail',
      'ActivityLog',
      'RunInterviewsLegacy',
    ].sort()

    const istProduktiveRouten = router
      .getRoutes()
      // Fix #1713: der SimulationLayout-Parent traegt selbst keinen Namen
      // (nur seine Kind-Routen StepSimulation/StepSimulationFeed sind
      // navigierbare Ziele) — er ist kein eigener Eintrag der SOLL-Liste.
      .filter((route) => route.redirect === undefined && route.name !== undefined)
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

  it('ohne Token: /settings/api-keys → Startseite (Bibliothek) mit authRequired + next', async () => {
    vi.mocked(getAgoraToken).mockReturnValue('')
    await pushAndSettle('/settings/api-keys')
    const route = router.currentRoute.value
    expect(route.name).toBe('LibraryRuns')
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
  ])('ohne Token: %s → Startseite (Bibliothek)', async (path) => {
    vi.mocked(getAgoraToken).mockReturnValue('')
    await pushAndSettle(path)
    expect(router.currentRoute.value.name).toBe('LibraryRuns')
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

describe('Router – Etappe 2 Adressen (#1797)', () => {
  beforeEach(() => {
    vi.mocked(getAgoraToken).mockReturnValue('tkn')
  })

  it.each([
    ['/library/runs', 'LibraryRuns'],
    ['/library/graphs', 'LibraryGraphs'],
    ['/simulations/sim_abc', 'RunOverview'],
    ['/simulations/sim_abc/graph', 'RunGraph'],
    ['/graphs/proj_abc', 'GraphLibraryDetail'],
    ['/compare', 'Compare'],
    ['/compare/sim_abc', 'Compare'],
    ['/activity/jobs', 'ActivityJobs'],
    ['/activity/jobs/run_abc', 'ActivityJobDetail'],
    ['/activity/log', 'ActivityLog'],
    ['/v4/simulation/sim_abc/interviews', 'RunInterviewsLegacy'],
  ])('löst %s → %s auf', async (path, name) => {
    await pushAndSettle(path)
    expect(router.currentRoute.value.name).toBe(name)
  })

  it('Lauf-Kinder hängen unter RunWorkspace und tragen simulationId', async () => {
    await pushAndSettle('/simulations/sim_abc/graph')
    const route = router.currentRoute.value
    expect(route.params.simulationId).toBe('sim_abc')
    expect(route.matched.map((m) => m.name)).toEqual(['RunWorkspace', 'RunGraph'])
  })

  it('reicht :projectId, :runId und die optionale Vergleichskennung durch', async () => {
    await pushAndSettle('/graphs/proj_abc')
    expect(router.currentRoute.value.params.projectId).toBe('proj_abc')
    await pushAndSettle('/activity/jobs/run_abc')
    expect(router.currentRoute.value.params.runId).toBe('run_abc')
    await pushAndSettle('/compare/sim_abc')
    expect(router.currentRoute.value.params.simulationId).toBe('sim_abc')
    await pushAndSettle('/compare')
    expect(router.currentRoute.value.params.simulationId).toBeFalsy()
  })

  it('Übergangsadresse trägt nur die simulationId, keine reportId', async () => {
    await pushAndSettle('/v4/simulation/sim_abc/interviews')
    const route = router.currentRoute.value
    expect(route.params.simulationId).toBe('sim_abc')
    expect(route.params.reportId).toBeUndefined()
  })

  it('Adressen späterer Etappen lösen unverändert auf', async () => {
    await pushAndSettle('/v4/interaction/report_abc')
    expect(router.currentRoute.value.name).toBe('StepInteraction')
    expect(router.currentRoute.value.params.reportId).toBe('report_abc')
    await pushAndSettle('/v4/simulation/sim_abc')
    expect(router.currentRoute.value.name).toBe('StepSimulation')
    await pushAndSettle('/process/project_42')
    expect(router.currentRoute.value.name).toBe('StepGraphBuild')
  })
})

describe('Router – Etappe 3 Einstellungsfenster (#1799)', () => {
  beforeEach(() => {
    vi.mocked(getAgoraToken).mockReturnValue('tkn')
    setActivePinia(createPinia())
  })

  it.each([
    ['/settings/general', 'SettingsGeneral'],
    ['/settings/embedding', 'SettingsEmbedding'],
    ['/settings/appearance', 'SettingsWindow'],
    ['/settings/providers', 'SettingsWindow'],
    ['/settings/profiles', 'SettingsWindow'],
    ['/settings/pipeline', 'SettingsWindow'],
    ['/settings/budgets', 'SettingsWindow'],
    ['/settings/access', 'SettingsWindow'],
    ['/settings/system', 'SettingsWindow'],
  ])('löst %s → %s auf und markiert es als Fenster', async (path, name) => {
    await pushAndSettle(path)
    expect(router.currentRoute.value.name).toBe(name)
    expect(router.currentRoute.value.meta.settingsWindow).toBe(true)
  })

  it('unbekannter Abschnitt → general', async () => {
    await pushAndSettle('/settings/gibt-es-nicht')
    expect(router.currentRoute.value.path).toBe('/settings/general')
    expect(router.currentRoute.value.name).toBe('SettingsGeneral')
  })

  it('die übrigen alten Einstellungsadressen bleiben bis Ticket 7 auf ihrer alten Ansicht', async () => {
    for (const [path, name] of [
      ['/settings/integrations', 'SettingsIntegrations'],
      ['/settings/profile', 'SettingsProfile'],
      ['/settings/api-keys', 'SettingsApiKeys'],
      ['/settings/audit-logs', 'SettingsAuditLogs'],
      ['/settings/llm-routing', 'SettingsLlmRouting'],
      ['/settings/llm-providers', 'SettingsLlmProviders'],
      ['/workspace/provider-keys', 'WorkspaceProviderKeys'],
    ] as const) {
      await pushAndSettle(path)
      expect(router.currentRoute.value.name).toBe(name)
      expect(router.currentRoute.value.meta.settingsWindow).toBeUndefined()
    }
  })

  it('Zugangsregel je Abschnitt: Abschnitte mit requiresAuth schicken ohne Token auf die Bibliothek', async () => {
    vi.mocked(getAgoraToken).mockReturnValue('')
    for (const section of ['providers', 'profiles', 'embedding']) {
      await pushAndSettle(`/settings/${section}`)
      expect(router.currentRoute.value.name, section).toBe('LibraryRuns')
    }
    // „Zugang" verlangt kein Token mehr: „Konto" war schon vorher ohne Token
    // erreichbar, Schlüssel und Audit-Protokoll sperrt der Abschnitt selbst.
    for (const section of ['general', 'appearance', 'pipeline', 'budgets', 'system', 'access']) {
      await pushAndSettle(`/settings/${section}`)
      expect(router.currentRoute.value.meta.settingsWindow, section).toBe(true)
    }
  })

  it('merkt sich beim Öffnen aus der App die Ansicht darunter, beim Abschnittswechsel unverändert', async () => {
    const store = useSettingsWindowStore()
    await pushAndSettle('/library/graphs')
    await pushAndSettle('/settings/budgets')
    expect(store.returnTo).toBe('/library/graphs')
    await pushAndSettle('/settings/system')
    expect(store.returnTo).toBe('/library/graphs')
    await pushAndSettle('/library/runs?view=running')
    expect(store.returnTo).toBeNull()
    await pushAndSettle('/settings/general')
    expect(store.returnTo).toBe('/library/runs?view=running')
  })
})
