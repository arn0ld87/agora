import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { getAgoraToken } from '../api/index'

const routes: RouteRecordRaw[] = [
  // Root → Dashboard (v4-AppShell ist Default-Einstieg)
  {
    path: '/',
    redirect: { name: 'Dashboard' },
  },

  // Landing (alte Editorial-Home unter /home erreichbar fuer Marketing/Fallback)
  {
    path: '/home',
    name: 'Home',
    component: () => import('../views/Home.vue'),
  },

  // Dashboard — AppShell-Wrapper (Slice F)
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('../views/v4/DashboardView.vue'),
  },
  // UX-Konsistenz: /v4/dashboard → /dashboard (alle v4-Step-Routes liegen unter /v4/*)
  {
    path: '/v4/dashboard',
    redirect: { name: 'Dashboard' },
  },

  // Runs — AppShell-Wrapper ersetzt direkte RunsView (Slice F)
  {
    path: '/runs',
    name: 'Runs',
    component: () => import('../views/v4/RunsAppShellView.vue'),
  },
  {
    path: '/runs/:id',
    name: 'RunDetail',
    component: () => import('../views/v4/RunDetailAppShellView.vue'),
    props: true,
  },

  // Settings — klassische View bleibt aktiv; /settings redirect auf /settings/general
  {
    path: '/settings',
    name: 'Settings',
    redirect: { name: 'SettingsGeneral' },
  },
  {
    path: '/settings/general',
    name: 'SettingsGeneral',
    component: () => import('../views/Settings/SettingsGeneralView.vue'),
  },
  {
    path: '/settings/integrations',
    name: 'SettingsIntegrations',
    component: () => import('../views/Settings/SettingsIntegrationsView.vue'),
  },
  {
    path: '/settings/users-teams',
    name: 'SettingsUsersTeams',
    component: () => import('../views/Settings/SettingsUsersTeamsView.vue'),
  },
  {
    path: '/settings/api-keys',
    name: 'SettingsApiKeys',
    component: () => import('../views/Settings/SettingsApiKeysView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/settings/audit-logs',
    name: 'SettingsAuditLogs',
    component: () => import('../views/Settings/SettingsAuditLogsView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/settings/llm-routing',
    name: 'SettingsLlmRouting',
    component: () => import('../views/Settings/LlmRoutingView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/settings/llm-providers',
    name: 'SettingsLlmProviders',
    component: () => import('../views/Settings/LlmProvidersView.vue'),
    meta: { requiresAuth: true },
  },
  // Klassische SettingsView bleibt erreichbar fuer Slice-G-Migration
  {
    path: '/settings-classic',
    name: 'SettingsClassic',
    component: () => import('../views/SettingsView.vue'),
  },

  // Legacy-Prozess-Routen
  {
    path: '/process/:projectId',
    name: 'Process',
    component: () => import('../views/MainView.vue'),
    props: true,
  },
  {
    path: '/simulation/:simulationId',
    name: 'Simulation',
    component: () => import('../views/SimulationView.vue'),
    props: true,
  },
  {
    path: '/simulation/:simulationId/start',
    name: 'SimulationRun',
    component: () => import('../views/SimulationRunView.vue'),
    props: true,
  },
  {
    path: '/report/:reportId',
    name: 'Report',
    component: () => import('../views/ReportView.vue'),
    props: true,
  },
  {
    path: '/interaction/:reportId',
    name: 'Interaction',
    component: () => import('../views/InteractionView.vue'),
    props: true,
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
  {
    path: '/v4/simulation/:simulationId',
    name: 'StepSimulation',
    component: () => import('../views/v4/steps/StepSimulationView.vue'),
    props: true,
  },
  {
    path: '/v4/simulation/:simulationId/feed',
    name: 'StepSimulationFeed',
    component: () => import('../views/v4/steps/StepSimulationFeedView.vue'),
    props: true,
  },
  {
    path: '/v4/report/:reportId',
    name: 'StepReport',
    component: () => import('../views/v4/steps/StepReportView.vue'),
    props: true,
  },
  {
    path: '/v4/interaction/:reportId',
    name: 'StepInteraction',
    component: () => import('../views/v4/steps/StepInteractionView.vue'),
    props: true,
  },

  // v4 compare + history (Slice I)
  {
    path: '/v4/compare/:simulationId',
    name: 'CompareV4',
    component: () => import('../views/v4/CompareView.vue'),
    props: true,
  },
  {
    path: '/v4/history',
    name: 'HistoryV4',
    component: () => import('../views/v4/HistoryView.vue'),
  },

  // Catch-all: unbekannte Pfade landen auf der NotFound-View statt leerer Shell.
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('../views/NotFoundView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (!to.meta?.requiresAuth) return true
  if (getAgoraToken()) return true
  return { name: 'Dashboard', query: { authRequired: '1', next: to.fullPath } }
})

export default router
