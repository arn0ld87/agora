import { createRouter, createWebHistory } from 'vue-router'
import type { RouteLocationAsRelativeGeneric, RouteLocationNormalized, RouteRecordRaw } from 'vue-router'
import { getAgoraToken } from '../api/index'
import { onboardingGuard } from './onboardingGuard'
import { parseConversationId } from '../composables/run/interviews/conversations'
import { useAuthStore } from '../store/auth'
import { safeNext } from '../auth/safeNext'
import {
  shelfObjectGuard,
  shelfRedirect,
  simulationFeedRedirect,
  simulationPostRedirect,
  simulationRoundsRedirect,
} from './legacyRedirects'
import {
  DEFAULT_SETTINGS_SECTION,
  getSettingsSection,
  isSettingsSectionId,
  normalizeSettingsSection,
  settingsSectionPath,
  type SettingsSectionId,
} from '../components/settings-window/sections'
import { isWindowRoute, useSettingsWindowStore } from '../stores/settingsWindow'

const AUTH_ONLY_ROUTES = { Login: 1, Register: 1, PasswordReset: 1, EmailConfirm: 1 } as const

/** Weiterleitung auf einen Abschnitt des Einstellungsfensters (Etappe 3, #1799). */
function settingsWindowRedirect(section: SettingsSectionId): RouteLocationAsRelativeGeneric {
  return { name: 'SettingsWindow', params: { section } }
}

const routes: RouteRecordRaw[] = [
  // Etappe 2 des Frontend-Umbaus (#1797, Ticket „Weiterleitungen"): die
  // Bibliothek ist die Startseite, das Dashboard entfaellt (Bauplan §6.2).
  // Alle alten Routen-Namen bleiben als Weiterleitungs-Routen bestehen, damit
  // kein `router.push({ name })` im Bestand bricht. Query und Hash bleiben
  // erhalten (vue-router uebernimmt sie, solange das Ziel sie nicht setzt).
  {
    path: '/',
    redirect: { name: 'LibraryRuns' },
  },

  // ADR-0010: /home → Startseite (Entfernungsrelease 1.0.0).
  {
    path: '/home',
    redirect: { name: 'LibraryRuns' },
  },

  // Dashboard entfaellt: der Start eines Laufs ist seit Etappe 3 der Startdialog
  // unter /library/runs/new (NewRun), die uebrigen Karten sind in Abschnitt
  // „Dashboard“ des Umsetzungsberichts aufgelistet. DashboardView.vue und
  // HeroNewRun.vue bleiben als Dateien stehen.
  {
    path: '/dashboard',
    name: 'Dashboard',
    redirect: { name: 'LibraryRuns' },
  },
  {
    path: '/v4/dashboard',
    redirect: { name: 'LibraryRuns' },
  },

  // /runs war die Listenansicht (Redesign PR 8: Ablage-Filter „lauf“), jetzt
  // die Bibliothek → Läufe.
  {
    path: '/runs',
    name: 'Runs',
    redirect: { name: 'LibraryRuns' },
  },
  // `/runs/:id` ist die Job-Detailansicht der RunRegistry; sie liegt jetzt unter
  // `/activity/jobs/:runId`, die Kennung bleibt unveraendert (gespeicherte
  // Links `/runs/<run_id>` oeffnen weiterhin den Job).
  {
    path: '/runs/:id',
    name: 'RunDetail',
    redirect: (to) => ({ name: 'ActivityJobDetail', params: { runId: String(to.params.id) } }),
  },

  // Onboarding — resumierbarer Erst-Einrichtungs-Wizard (Onboarding Slice 2)
  {
    path: '/onboarding',
    name: 'Onboarding',
    component: () => import('../views/onboarding/OnboardingView.vue'),
    // Prozessweiter Betreiber-Zustand (operator_only im Backend, #1617)
    meta: { operatorOnly: true },
  },

  // Settings — /settings und der klassische Deep-Link konvergieren auf General.
  {
    path: '/settings',
    name: 'Settings',
    redirect: { name: 'SettingsGeneral' },
  },
  // Etappe 3 (#1799): `/settings/general` und `/settings/embedding` zeigen das
  // Einstellungsfenster auf ihrem Abschnitt; die Ansicht darunter rendert
  // App.vue (meta.settingsWindow). Die Namen bleiben fuer bestehende Aufrufer.
  {
    path: '/settings/general',
    name: 'SettingsGeneral',
    component: () => import('../components/settings-window/SettingsWindow.vue'),
    // Prozessweiter Betreiber-Zustand (operator_only im Backend, #1617)
    meta: { operatorOnly: true, settingsWindow: true, settingsSection: 'general' },
  },
  // Alle uebrigen Abschnitte des Fensters (`/settings/appearance` …). Unbekannter
  // Abschnitt → general.
  {
    path: '/settings/:section',
    name: 'SettingsWindow',
    component: () => import('../components/settings-window/SettingsWindow.vue'),
    meta: { settingsWindow: true },
  },
  // Etappe 3 (#1799, Bauplan §6.2): die alten Einstellungsadressen leiten auf
  // das Fenster um. Die Namen bleiben als Weiterleitungs-Routen bestehen, damit
  // kein `router.push({ name })` im Bestand bricht; Query und Hash bleiben
  // erhalten. Die Zugangsregeln gelten am Ziel (sections.ts), nicht an der
  // alten Adresse. Statische Adressen gewinnen gegen `/settings/:section`.
  { path: '/settings/integrations', name: 'SettingsIntegrations', redirect: settingsWindowRedirect('pipeline') },
  { path: '/settings/profile', name: 'SettingsProfile', redirect: settingsWindowRedirect('profile') },
  // Legacy-Adresse für die persönliche Profilansicht im eigenen Abschnitt.
  { path: '/settings/users-teams', name: 'SettingsUsersTeams', redirect: settingsWindowRedirect('access') },
  { path: '/settings/api-keys', name: 'SettingsApiKeys', redirect: settingsWindowRedirect('access') },
  { path: '/settings/audit-logs', name: 'SettingsAuditLogs', redirect: settingsWindowRedirect('access') },
  { path: '/settings/llm-routing', name: 'SettingsLlmRouting', redirect: settingsWindowRedirect('profiles') },
  { path: '/settings/llm-providers', name: 'SettingsLlmProviders', redirect: settingsWindowRedirect('providers') },
  { path: '/workspace/provider-keys', name: 'WorkspaceProviderKeys', redirect: settingsWindowRedirect('providers') },
  // Onboarding Slice 4.3.3: eigene Route für die kanonische
  // Embedding-Konfiguration (Store, View, Migrations, Ollama-Download).
  {
    path: '/settings/embedding',
    name: 'SettingsEmbedding',
    component: () => import('../components/settings-window/SettingsWindow.vue'),
    meta: { operatorOnly: true, requiresAuth: true, settingsWindow: true, settingsSection: 'embedding' },
  },
  // Legacy-Deep-Link bleibt fuer einen Release-Zyklus als Redirect erhalten.
  {
    path: '/settings-classic',
    redirect: { name: 'SettingsGeneral' },
  },

  // Legacy-Prozess-Routen
  {
    path: '/process/:projectId',
    name: 'Process',
    // Query explizit mitnehmen: der Dashboard-Start hängt die Run-Parameter
    // (Rundenzahl, Budget) an diese Route. Ein Redirect, der sie nicht nennt,
    // verwirft sie — der Start landete dann auf Reset-Defaults (Issue #1234).
    redirect: (to) => ({
      name: 'StepGraphBuild',
      params: { projectId: String(to.params.projectId) },
      query: to.query,
    }),
  },
  {
    path: '/simulation/:simulationId',
    name: 'Simulation',
    redirect: simulationFeedRedirect,
  },
  {
    path: '/simulation/:simulationId/start',
    name: 'SimulationRun',
    redirect: simulationFeedRedirect,
  },
  {
    path: '/report/:reportId',
    name: 'Report',
    redirect: (to) => ({ name: 'StepReport', params: { reportId: String(to.params.reportId) } }),
  },
  {
    path: '/interaction/:reportId',
    name: 'Interaction',
    redirect: (to) => ({ name: 'StepInteraction', params: { reportId: String(to.params.reportId) } }),
  },

  // v4 step shell wrappers (Slice H) — /v4/* prefix
  {
    path: '/v4/graph-build/:projectId',
    name: 'StepGraphBuild',
    component: () => import('../views/v4/steps/StepGraphBuildView.vue'),
    props: true,
  },
  {
    path: '/v4/env-setup/:projectId',
    name: 'StepEnvSetup',
    component: () => import('../views/v4/steps/StepEnvSetupView.vue'),
    props: true,
  },
  // Etappe 4 (#1801, Bauplan §6.2): Die Simulation ist ein Reiter am Lauf
  // (/simulations/:id/simulation/…). Die alten Namen bleiben als Weiterleitungen
  // bestehen; Query und Hash bleiben erhalten. Die Übergangsadresse
  // `/v4/simulation/:id/interviews` (RunInterviewsLegacy) ist eine eigene Route
  // weiter unten und von diesen Einträgen nicht betroffen.
  { path: '/v4/simulation/:simulationId', name: 'StepSimulation', redirect: simulationFeedRedirect },
  { path: '/v4/simulation/:simulationId/feed', name: 'StepSimulationFeed', redirect: simulationFeedRedirect },
  { path: '/v4/simulation/:simulationId/threads', name: 'SimThreads', redirect: simulationFeedRedirect },
  { path: '/v4/simulation/:simulationId/thread/:postId', name: 'SimThreadFocus', redirect: simulationPostRedirect },
  { path: '/v4/simulation/:simulationId/rounds', name: 'SimRounds', redirect: simulationRoundsRedirect },
  { path: '/v4/simulation/:simulationId/actions', name: 'SimActions', redirect: simulationRoundsRedirect },
  // `/live` zeigte ein Vollbild-Instrument ohne Anschluss an die Tab-Navigation;
  // das Ziel ist die Runden-Ansicht.
  {
    path: '/v4/simulation/:simulationId/live',
    redirect: simulationRoundsRedirect,
  },
  // Etappe 5 (#1804, Bauplan 6.2): der Bericht ist ein Reiter am Lauf
  // (/simulations/:id/report/:reportId?). Die alte Adresse loest die Simulation
  // aus dem Bericht auf und leitet um (ReportRedirectView); der Name bleibt, damit
  // Aufrufer ohne bekannte Simulation weiter `{ name: 'StepReport' }` nutzen.
  // `/report/:reportId` (Name `Report`) leitet oben auf diese Adresse.
  {
    path: '/v4/report/:reportId',
    name: 'StepReport',
    component: () => import('../views/run/report/ReportRedirectView.vue'),
    props: true,
  },
  // #1790: Die alte Gesprächsansicht ist entfernt. Der Parameter ist eine
  // Berichts-ID: dieselbe Auflösung wie bei `StepReport` (ReportRedirectView),
  // Ziel ist die rechte Spalte "Nachfragen" des Berichts (`?panel=questions`).
  // Query und Hash bleiben erhalten; ein vorhandenes `?panel=` gewinnt.
  {
    path: '/v4/interaction/:reportId',
    name: 'StepInteraction',
    component: () => import('../views/run/report/ReportRedirectView.vue'),
    props: (to) => ({ reportId: String(to.params.reportId), panel: 'questions' }),
  },

  // v4 compare + history (Slice I)
  {
    path: '/v4/compare/:simulationId',
    name: 'CompareV4',
    redirect: (to) => ({ name: 'Compare', params: { simulationId: String(to.params.simulationId) } }),
  },
  // History → Aktivität → Jobs (Etappe 2).
  {
    path: '/v4/history',
    name: 'HistoryV4',
    redirect: { name: 'ActivityJobs' },
  },

  // Die Ablage-Startseite ist zur Bibliothek geworden: `/ablage?filter=…`
  // leitet je Filter um (shelfRedirect). Der Name `Shelf` bleibt fuer Aufrufer
  // bestehen.
  {
    path: '/ablage',
    name: 'Shelf',
    redirect: shelfRedirect,
  },
  // Lauf und Graph leitet `beforeEnter` um; Bericht und Personasatz bleiben bis
  // Etappe 5 bzw. 7 auf der alten Ablage-Ansicht (Bauplan §6.2). Ein einziger
  // Eintrag, damit `{ name: 'ShelfObject', params: { kind } }` fuer alle vier
  // Arten aufloesbar bleibt.
  {
    path: '/ablage/:kind(lauf|bericht|personasatz|graph)/:objectId',
    name: 'ShelfObject',
    component: () => import('../views/shell/ShelfView.vue'),
    props: true,
    meta: { layout: 'flush' },
    beforeEnter: shelfObjectGuard,
  },

  // Etappe 2 des Frontend-Umbaus (#1797, Ticket „Adressen"): neue Adressen
  // nach docs/plans/active/frontend-umbau.md §6.1. Die alten Adressen der
  // Etappe 2 leiten oben und in legacyRedirects.ts hierher um; alle spaeteren
  // Zeilen aus §6.2 bleiben auf ihren alten Ansichten. Pfade englisch,
  // Beschriftungen deutsch.
  {
    path: '/library/runs',
    name: 'LibraryRuns',
    component: () => import('../views/library/LibraryRunsView.vue'),
  },
  // Startdialog „Neuer Lauf“ (#1799, Etappe 3): liegt wie das Einstellungsfenster
  // als Fenster ueber der zuletzt gezeigten Ansicht (meta.windowOverBackground).
  {
    path: '/library/runs/new',
    name: 'NewRun',
    component: () => import('../views/library/NewRunView.vue'),
    meta: { windowOverBackground: true },
  },
  {
    path: '/library/graphs',
    name: 'LibraryGraphs',
    component: () => import('../views/library/LibraryGraphsView.vue'),
  },
  // Etappe 7 (#1807, Skelett): Personasaetze als Bibliotheksobjekt. Reiter und
  // Seitenleiste zeigen noch nicht hierher; Weiterleitungen folgen mit den
  // Folgetickets (§6.2).
  {
    path: '/library/persona-sets',
    name: 'LibraryPersonaSets',
    component: () => import('../views/library/LibraryPersonaSetsView.vue'),
  },
  {
    path: '/persona-sets/:setId',
    name: 'PersonaSet',
    component: () => import('../views/persona-sets/PersonaSetView.vue'),
    props: true,
  },
  // Lauf-Arbeitsbereich unter /simulations/…, nicht /runs/…: `/runs/:id` ist
  // die Job-Detailansicht der RunRegistry (§6). Reiter Personas, Simulation,
  // Bericht, Interviews bekommen ihre Kind-Routen mit den spaeteren Etappen.
  {
    path: '/simulations/:simulationId',
    name: 'RunWorkspace',
    component: () => import('../views/run/RunWorkspaceView.vue'),
    props: true,
    children: [
      {
        path: '',
        name: 'RunOverview',
        component: () => import('../views/run/RunOverviewView.vue'),
      },
      {
        path: 'graph',
        name: 'RunGraph',
        component: () => import('../views/run/RunGraphView.vue'),
      },
      // Etappe 4 (#1801): Simulation als Reiter mit Unterreitern. Die Adresse
      // selbst (leerer Kindpfad) fuehrt auf den Feed; die Kinder rendern in der
      // Huelle.
      {
        path: 'simulation',
        name: 'RunSimulation',
        component: () => import('../views/run/simulation/RunSimulationView.vue'),
        props: true,
        children: [
          {
            path: '',
            name: 'RunSimulationIndex',
            redirect: (to) => ({
              name: 'RunSimulationFeed',
              params: { simulationId: String(to.params.simulationId) },
              query: to.query,
              hash: to.hash,
            }),
          },
          {
            path: 'feed/:network(twitter|reddit)?',
            name: 'RunSimulationFeed',
            component: () => import('../views/run/simulation/RunSimulationFeedView.vue'),
            props: true,
          },
          {
            path: 'post/:postId',
            name: 'RunSimulationPost',
            component: () => import('../views/run/simulation/RunSimulationPostView.vue'),
            props: true,
          },
          {
            path: 'rounds',
            name: 'RunSimulationRounds',
            component: () => import('../views/run/simulation/RunSimulationRoundsView.vue'),
            props: true,
          },
          {
            path: 'diagnostics',
            name: 'RunSimulationDiagnostics',
            component: () => import('../views/run/simulation/RunSimulationDiagnosticsView.vue'),
            props: true,
          },
        ],
      },
      // Etappe 5 (#1804): Bericht als Reiter. Ohne `reportId` die juengste
      // Fassung; `new` (PENDING_REPORT_ID) bietet den Start an. Query:
      // `?claim=`, `?section=`, `?panel=evidence|questions`.
      {
        path: 'report/:reportId?',
        name: 'RunReport',
        component: () => import('../views/run/report/RunReportView.vue'),
        props: true,
      },
      // Etappe 7 (#1807, Skelett): Personas am Lauf.
      {
        path: 'personas',
        name: 'RunPersonas',
        component: () => import('../views/run/personas/RunPersonasView.vue'),
        props: true,
      },
      // Etappe 6 (#1805): Interviews am Lauf. `conversationId` ist `persona-<n>`
      // oder `group-<kennung>`; alles andere erreicht die View als fehlender Param.
      {
        path: 'interviews/:conversationId?',
        name: 'RunInterviews',
        component: () => import('../views/run/interviews/RunInterviewsView.vue'),
        props: (route) => {
          const raw = route.params.conversationId
          const id = Array.isArray(raw) ? raw[0] : raw
          return {
            simulationId: String(route.params.simulationId),
            conversationId: parseConversationId(id) ? id : undefined,
          }
        },
      },
    ],
  },
  {
    path: '/graphs/:projectId',
    name: 'GraphLibraryDetail',
    component: () => import('../views/graph/GraphLibraryDetailView.vue'),
    props: true,
  },
  {
    path: '/compare/:simulationId?',
    name: 'Compare',
    component: () => import('../views/v4/CompareView.vue'),
    props: true,
  },
  {
    path: '/activity/jobs',
    name: 'ActivityJobs',
    component: () => import('../views/activity/ActivityJobsView.vue'),
  },
  // `:runId` ist die Job-Kennung (`run_…`) wie bei `/runs/:id`; dieselbe
  // Detailansicht, die Kennung kommt aus `params.runId`.
  {
    path: '/activity/jobs/:runId',
    name: 'ActivityJobDetail',
    component: () => import('../views/v4/RunDetailAppShellView.vue'),
    props: true,
  },
  {
    path: '/activity/log',
    name: 'ActivityLog',
    component: () => import('../views/activity/ActivityLogView.vue'),
  },
  // Alte Uebergangsadresse (Etappe 2): seit Etappe 6 (#1805) eine Weiterleitung
  // auf den Interviews-Reiter. Query und Hash bleiben erhalten.
  {
    path: '/v4/simulation/:simulationId/interviews',
    name: 'RunInterviewsLegacy',
    redirect: (to) => ({
      name: 'RunInterviews',
      params: { simulationId: String(to.params.simulationId) },
      query: to.query,
      hash: to.hash,
    }),
  },

  // Auth-Routen (#1617, Teil B1)
  {
    path: '/auth/login',
    name: 'Login',
    component: () => import('../views/auth/LoginView.vue'),
    meta: { public: true, layout: 'bare' },
  },
  {
    path: '/auth/register',
    name: 'Register',
    component: () => import('../views/auth/RegisterView.vue'),
    meta: { public: true, layout: 'bare' },
  },
  {
    path: '/auth/reset',
    name: 'PasswordReset',
    component: () => import('../views/auth/PasswordResetView.vue'),
    meta: { public: true, layout: 'bare' },
  },
  {
    path: '/auth/confirm',
    name: 'EmailConfirm',
    component: () => import('../views/auth/EmailConfirmView.vue'),
    meta: { public: true, layout: 'bare' },
  },

  // Catch-all: unbekannte Pfade landen auf der NotFound-View statt leerer Shell.
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('../views/NotFoundView.vue'),
    meta: { layout: 'bare' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

/**
 * Zugangsregeln einer Route. Das Einstellungsfenster liest sie je Abschnitt
 * aus `sections.ts` (eine Route, neun Regeln); alle anderen aus `meta`.
 */
function routeAccess(to: RouteLocationNormalized): { operatorOnly: boolean; requiresAuth: boolean } {
  if (to.meta?.settingsWindow === true) {
    const section = getSettingsSection(
      normalizeSettingsSection(to.meta.settingsSection ?? to.params.section),
    )
    return { operatorOnly: section.operatorOnly, requiresAuth: section.requiresAuth }
  }
  return { operatorOnly: !!to.meta?.operatorOnly, requiresAuth: !!to.meta?.requiresAuth }
}

// Unbekannter Abschnitt des Einstellungsfensters → general. Globaler Guard
// statt `beforeEnter`: der feuert bei Parameterwechsel innerhalb derselben
// Route nicht.
router.beforeEach((to) => {
  if (to.name === 'SettingsWindow' && !isSettingsSectionId(to.params.section)) {
    return { path: settingsSectionPath(DEFAULT_SETTINGS_SECTION), replace: true }
  }
  return true
})

router.beforeEach(async (to) => {
  let auth: ReturnType<typeof useAuthStore> | null = null
  try {
    auth = useAuthStore()
  } catch {
    // Pinia noch nicht aktiv (z.B. Unit-Tests ohne Store).
  }
  if (auth) await auth.ensureInit()

  // JWT-Modus (#1617): ohne Session nur öffentliche Routen.
  if (auth?.jwtEnabled) {
    // Session ohne Workspace (Passwort-Reset über den Mail-Link): nur Reset
    // und Login sind erreichbar, auch keine anderen öffentlichen Routen.
    if (auth.sessionWithoutWorkspace) {
      if (to.name === 'PasswordReset' || to.name === 'Login') return true
      if (auth.passwordRecovery) return { name: 'PasswordReset' }
      return to.meta?.public ? { name: 'Login' } : { name: 'Login', query: { next: to.fullPath } }
    }
    if (to.meta?.public) {
      if (to.name === 'Login' && auth.isAuthenticated) return safeNext(to.query.next)
      return true
    }
    if (!auth.isAuthenticated) return { name: 'Login', query: { next: to.fullPath } }
    // Einstellungen und Onboarding sind Betreiber-Zustand; das Backend
    // antwortet Supabase-Nutzern dort mit 403. Besucher mit Session sehen
    // stattdessen eine nicht-editierbare Vorschau (DemoPreviewFrame) statt
    // eines Redirects — kein separater Zustand fuer "kein Zugang und keine
    // Vorschau" existiert, solange eine Session vorliegt.
    if (routeAccess(to).operatorOnly && !auth.operatorAccess && !auth.demoPreview) return '/'
    return true
  }

  // Ohne JWT bleibt nur die Token-Anmeldung; mit Token geht es direkt weiter.
  if (to.name === 'Login') {
    return getAgoraToken() ? safeNext(to.query.next) : true
  }

  // Ohne JWT gibt es keine Registrierung oder Bestätigung.
  if (to.meta?.public && String(to.name ?? '') in AUTH_ONLY_ROUTES) return '/'

  // Legacy-Guard: requiresAuth-Routen ohne Token auf die Startseite (Bibliothek).
  if (!routeAccess(to).requiresAuth) return true
  if (getAgoraToken()) return true
  return { name: 'LibraryRuns', query: { authRequired: '1', next: to.fullPath } }
})

// Onboarding-Redirect — läuft NACH dem Auth-Guard (Onboarding Slice 2).
router.beforeEach(onboardingGuard)

// Einstellungsfenster (#1799): beim Öffnen aus der App die Ansicht darunter
// merken, beim Verlassen vergessen. Ein Direktaufruf (`from` ohne Treffer)
// merkt nichts — das Fenster liegt dann über der Bibliothek der Läufe.
router.afterEach((to, from, failure) => {
  if (failure) return
  let store: ReturnType<typeof useSettingsWindowStore> | null = null
  try {
    store = useSettingsWindowStore()
  } catch {
    // Pinia noch nicht aktiv (z.B. Unit-Tests ohne Store).
    return
  }
  if (!isWindowRoute(to.meta)) {
    store.reset()
  } else if (!isWindowRoute(from.meta)) {
    store.open(from.matched.length > 0 ? from.fullPath : null)
  }
})

export default router
