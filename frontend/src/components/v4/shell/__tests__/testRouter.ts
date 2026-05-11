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
  { path: '/settings',               name: 'Settings',            redirect: '/settings/general' },
  { path: '/settings/general',       name: 'SettingsGeneral',     component: stub },
  { path: '/settings/integrations',  name: 'SettingsIntegrations',component: stub },
  { path: '/settings/users-teams',   name: 'SettingsUsersTeams',  component: stub },
  { path: '/settings/api-keys',      name: 'SettingsApiKeys',     component: stub },
  { path: '/settings/audit-logs',    name: 'SettingsAuditLogs',   component: stub },
  { path: '/settings/llm-routing',   name: 'SettingsLlmRouting',  component: stub },
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
