import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { getAgoraToken } from '../api/index'
import { onboardingGuard } from './onboardingGuard'
import { useShellVariant } from '../composables/useShellVariant'

const routes: RouteRecordRaw[] = [
  // Root → Dashboard (classic) bzw. Ablage (dossier).
  // Block B3: die EINZIGE Auswertung des Shell-Flags neben /ablage selbst.
  {
    path: '/',
    redirect: () =>
      useShellVariant().variant.value === 'dossier'
        ? { name: 'Shelf' }
        : { name: 'Dashboard' },
  },

  // ADR-0010: /home → /dashboard (Entfernungsrelease 1.0.0; Home.vue bleibt bis dahin physisch erhalten).
  {
    path: '/home',
    redirect: { name: 'Dashboard' },
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

  // Onboarding — resumierbarer Erst-Einrichtungs-Wizard (Onboarding Slice 2)
  {
    path: '/onboarding',
    name: 'Onboarding',
    component: () => import('../views/onboarding/OnboardingView.vue'),
  },

  // Settings — /settings und der klassische Deep-Link konvergieren auf General.
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
    path: '/settings/profile',
    name: 'SettingsProfile',
    component: () => import('../views/Settings/SettingsProfileView.vue'),
  },
  // Sidebar-IA-Fix (Onboarding-Epic): "Users & Teams" wurde durch das
  // Profil-Setting ersetzt — bestehende Deep-Links leiten weiter um.
  {
    path: '/settings/users-teams',
    name: 'SettingsUsersTeams',
    redirect: { name: 'SettingsProfile' },
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
  // Onboarding Slice 4.3.3: eigene Route für die kanonische
  // Embedding-Konfiguration (Store, View, Migrations, Ollama-Download).
  {
    path: '/settings/embedding',
    name: 'SettingsEmbedding',
    component: () => import('../views/Settings/EmbeddingConfigurationsView.vue'),
    meta: { requiresAuth: true },
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
    redirect: (to) => ({ name: 'StepEnvSetup', params: { projectId: String(to.params.simulationId) } }),
  },
  {
    path: '/simulation/:simulationId/start',
    name: 'SimulationRun',
    redirect: (to) => ({ name: 'StepSimulation', params: { simulationId: String(to.params.simulationId) } }),
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

  // Block B3 — Neuhuelle „Richtung B · Dossier“ (PLAN.md).
  // /ablage ist der Einstieg der neuen Shell. Der Feature-Flag
  // (useShellVariant) wird NUR hier und im Dashboard-Redirect unten
  // ausgewertet — nie tief in Komponenten.
  {
    path: '/ablage',
    name: 'Shelf',
    component: () => import('../views/shell/ShelfView.vue'),
  },
  {
    path: '/ablage/:kind(lauf|bericht|personasatz|graph)/:objectId',
    name: 'ShelfObject',
    component: () => import('../views/shell/ShelfView.vue'),
    props: true,
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

// Onboarding-Redirect — läuft NACH dem Auth-Guard (Onboarding Slice 2).
router.beforeEach(onboardingGuard)

export default router
