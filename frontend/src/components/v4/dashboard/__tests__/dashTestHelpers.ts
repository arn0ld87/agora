/**
 * Test-Helper für Dashboard-Specs — i18n + Router-Setup an einer Stelle.
 */
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

import de from '../../../../i18n/locales/de.json'
import en from '../../../../i18n/locales/en.json'

export function makeI18n(locale: 'de' | 'en' = 'de') {
  return createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'en',
    messages: { de, en },
  })
}

const stub = { template: '<div/>' }

const BASE_ROUTES: RouteRecordRaw[] = [
  { path: '/', name: 'Home', component: stub },
  { path: '/dashboard', name: 'Dashboard', component: stub },
  { path: '/process/:projectId', name: 'Process', component: stub },
  { path: '/runs', name: 'Runs', component: stub },
  { path: '/runs/:id', name: 'RunDetail', component: stub },
  { path: '/report/:reportId', name: 'Report', component: stub },
  { path: '/v4/compare/:simulationId', name: 'CompareV4', component: stub },
  { path: '/v4/compare/last', name: 'CompareV4Last', component: stub },
  { path: '/v4/history', name: 'HistoryV4', component: stub },
  { path: '/settings/general', name: 'SettingsGeneral', component: stub },
]

export function makeRouter(extra: RouteRecordRaw[] = []) {
  return createRouter({
    history: createMemoryHistory(),
    routes: [...BASE_ROUTES, ...extra],
  })
}
