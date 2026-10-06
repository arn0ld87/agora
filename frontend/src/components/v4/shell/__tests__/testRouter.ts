/**
 * testRouter — gemeinsamer Router-Helper fuer Shell-Specs (Gap 4, Slice F).
 *
 * Erzeugt einen Memory-Router mit den Kern-Routes der AppShell
 * plus optionalen Extra-Routes fuer view-spezifische Tests.
 */
import { createRouter, createMemoryHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const stub = { template: '<div/>' }

const BASE_ROUTES: RouteRecordRaw[] = [
  { path: '/',                       name: 'Home',                component: stub },
  { path: '/dashboard',              name: 'Dashboard',           component: stub },
  { path: '/runs',                   name: 'Runs',                component: stub },
  { path: '/runs/:id',               name: 'RunDetail',           component: stub },
  { path: '/ablage',                 name: 'Shelf',               component: stub },
  { path: '/ablage/:kind(lauf|bericht|personasatz|graph)/:objectId', name: 'ShelfObject', component: stub },
  { path: '/v4/compare/:simulationId', name: 'CompareV4',         component: stub },
  // Etappe 2 (#1797): neue Adressen der Bibliothek, des Laufs und der Aktivitaet.
  { path: '/library/runs',           name: 'LibraryRuns',         component: stub },
  { path: '/library/runs/new',       name: 'NewRun',              component: stub },
  { path: '/library/graphs',         name: 'LibraryGraphs',       component: stub },
  { path: '/simulations/:simulationId', name: 'RunOverview',      component: stub },
  { path: '/graphs/:projectId',      name: 'GraphLibraryDetail',  component: stub },
  { path: '/compare/:simulationId?', name: 'Compare',             component: stub },
  { path: '/activity/jobs',          name: 'ActivityJobs',        component: stub },
  { path: '/activity/jobs/:runId',   name: 'ActivityJobDetail',   component: stub },
  { path: '/activity/log',           name: 'ActivityLog',         component: stub },
  { path: '/settings',               name: 'Settings',            redirect: '/settings/general' },
  { path: '/settings/general',       name: 'SettingsGeneral',     component: stub },
  { path: '/settings/integrations',  name: 'SettingsIntegrations',component: stub },
  { path: '/settings/users-teams',   name: 'SettingsUsersTeams',  redirect: '/settings/profile' },
  { path: '/settings/profile',       name: 'SettingsProfile',     component: stub },
  { path: '/settings/api-keys',      name: 'SettingsApiKeys',     component: stub },
  { path: '/settings/audit-logs',    name: 'SettingsAuditLogs',   component: stub },
  { path: '/settings/llm-providers', name: 'SettingsLlmProviders',component: stub },
  { path: '/settings/llm-routing',   name: 'SettingsLlmRouting',  component: stub },
  { path: '/settings/embedding',     name: 'SettingsEmbedding',   component: stub },
  { path: '/onboarding',             name: 'Onboarding',          component: stub },
  { path: '/workspace/provider-keys', name: 'WorkspaceProviderKeys', component: stub },
]

/**
 * Erstellt einen isolierten Memory-Router fuer Unit-Tests.
 *
 * @param extraRoutes  Optionale zusaetzliche Routes (z.B. fuer view-spezifische Tests)
 */
export function makeTestRouter(extraRoutes: RouteRecordRaw[] = []) {
  return createRouter({
    history: createMemoryHistory(),
    routes: [...BASE_ROUTES, ...extraRoutes],
  })
}
