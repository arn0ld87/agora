import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import Home from '../views/Home.vue'
import MainView from '../views/MainView.vue'
import SimulationView from '../views/SimulationView.vue'
import SimulationRunView from '../views/SimulationRunView.vue'
import ReportView from '../views/ReportView.vue'
import InteractionView from '../views/InteractionView.vue'
import SettingsView from '../views/SettingsView.vue'

const routes: RouteRecordRaw[] = [
  // Landing (bleibt unveraendert)
  {
    path: '/',
    name: 'Home',
    component: Home,
  },

  // Dashboard — AppShell-Wrapper (Slice F)
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('../views/v4/DashboardView.vue'),
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
  },
  {
    path: '/settings/audit-logs',
    name: 'SettingsAuditLogs',
    component: () => import('../views/Settings/SettingsAuditLogsView.vue'),
  },
  {
    path: '/settings/llm-routing',
    name: 'SettingsLlmRouting',
    component: () => import('../views/Settings/LlmRoutingView.vue'),
  },
  // Klassische SettingsView bleibt erreichbar fuer Slice-G-Migration
  {
    path: '/settings-classic',
    name: 'SettingsClassic',
    component: SettingsView,
  },

  // Legacy-Prozess-Routen
  {
    path: '/process/:projectId',
    name: 'Process',
    component: MainView,
    props: true,
  },
  {
    path: '/simulation/:simulationId',
    name: 'Simulation',
    component: SimulationView,
    props: true,
  },
  {
    path: '/simulation/:simulationId/start',
    name: 'SimulationRun',
    component: SimulationRunView,
    props: true,
  },
  {
    path: '/report/:reportId',
    name: 'Report',
    component: ReportView,
    props: true,
  },
  {
    path: '/interaction/:reportId',
    name: 'Interaction',
    component: InteractionView,
    props: true,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
