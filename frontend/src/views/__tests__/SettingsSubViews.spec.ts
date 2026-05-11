/**
 * SettingsSubViews — Smoke-Tests fuer die 5 neuen dedicated Settings-Routes (Slice F).
 *
 * Prueft: mountet ohne Crash, korrekte Breadcrumbs, Stub-Hinweis vorhanden.
 */
import { describe, expect, it, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { makeTestRouter } from '@/components/v4/shell/__tests__/testRouter'

vi.mock('@/components/v4/shell/AppShell.vue', () => ({
  default: {
    name: 'AppShell',
    props: ['breadcrumbs'],
    template: '<div class="app-shell-stub" data-breadcrumbs="true"><slot /></div>',
  },
}))
vi.mock('@/components/v4/shell/PageHeader.vue', () => ({
  default: {
    name: 'PageHeader',
    props: ['title', 'subtitle'],
    template: '<div class="page-header-stub"><h1>{{ title }}</h1></div>',
  },
}))
vi.mock('@/components/v4/forms/Card.vue', () => ({
  default: {
    name: 'Card',
    props: ['title'],
    template: '<div class="card-stub"><slot /></div>',
  },
}))

import SettingsGeneralView from '../Settings/SettingsGeneralView.vue'
import SettingsIntegrationsView from '../Settings/SettingsIntegrationsView.vue'
import SettingsUsersTeamsView from '../Settings/SettingsUsersTeamsView.vue'
import SettingsApiKeysView from '../Settings/SettingsApiKeysView.vue'
import SettingsAuditLogsView from '../Settings/SettingsAuditLogsView.vue'

async function mountView(component: object, path: string) {
  const router = makeTestRouter()
  const pinia = createPinia()
  setActivePinia(pinia)
  await router.push(path)
  await router.isReady()
  const wrapper = mount(component, {
    global: { plugins: [router, pinia] },
  })
  await flushPromises()
  return wrapper
}

describe('SettingsGeneralView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('mountet ohne Crash', async () => {
    const w = await mountView(SettingsGeneralView, '/settings/general')
    expect(w.exists()).toBe(true)
  })

  it('rendert Breadcrumb "General"', async () => {
    const w = await mountView(SettingsGeneralView, '/settings/general')
    const shell = w.findComponent({ name: 'AppShell' })
    const crumbs = shell.props('breadcrumbs') as Array<{ label: string }>
    expect(crumbs.map((c) => c.label)).toContain('General')
  })

  it('rendert PageHeader mit Titel "General"', async () => {
    const w = await mountView(SettingsGeneralView, '/settings/general')
    expect(w.find('.page-header-stub h1').text()).toBe('General')
  })

  it('zeigt Stub-Hinweis auf Slice G', async () => {
    const w = await mountView(SettingsGeneralView, '/settings/general')
    expect(w.text()).toContain('Slice G')
  })
})

describe('SettingsIntegrationsView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('mountet ohne Crash', async () => {
    const w = await mountView(SettingsIntegrationsView, '/settings/integrations')
    expect(w.exists()).toBe(true)
  })

  it('rendert Breadcrumb "Integrations"', async () => {
    const w = await mountView(SettingsIntegrationsView, '/settings/integrations')
    const shell = w.findComponent({ name: 'AppShell' })
    const crumbs = shell.props('breadcrumbs') as Array<{ label: string }>
    expect(crumbs.map((c) => c.label)).toContain('Integrations')
  })

  it('zeigt Stub-Hinweis auf Slice G', async () => {
    const w = await mountView(SettingsIntegrationsView, '/settings/integrations')
    expect(w.text()).toContain('Slice G')
  })
})

describe('SettingsUsersTeamsView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('mountet ohne Crash', async () => {
    const w = await mountView(SettingsUsersTeamsView, '/settings/users-teams')
    expect(w.exists()).toBe(true)
  })

  it('rendert Breadcrumb "Users & Teams"', async () => {
    const w = await mountView(SettingsUsersTeamsView, '/settings/users-teams')
    const shell = w.findComponent({ name: 'AppShell' })
    const crumbs = shell.props('breadcrumbs') as Array<{ label: string }>
    expect(crumbs.map((c) => c.label)).toContain('Users & Teams')
  })

  it('zeigt Stub-Hinweis auf Slice G', async () => {
    const w = await mountView(SettingsUsersTeamsView, '/settings/users-teams')
    expect(w.text()).toContain('Slice G')
  })
})

describe('SettingsApiKeysView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('mountet ohne Crash', async () => {
    const w = await mountView(SettingsApiKeysView, '/settings/api-keys')
    expect(w.exists()).toBe(true)
  })

  it('rendert Breadcrumb "API Keys"', async () => {
    const w = await mountView(SettingsApiKeysView, '/settings/api-keys')
    const shell = w.findComponent({ name: 'AppShell' })
    const crumbs = shell.props('breadcrumbs') as Array<{ label: string }>
    expect(crumbs.map((c) => c.label)).toContain('API Keys')
  })

  it('zeigt Stub-Hinweis auf Slice G', async () => {
    const w = await mountView(SettingsApiKeysView, '/settings/api-keys')
    expect(w.text()).toContain('Slice G')
  })
})

describe('SettingsAuditLogsView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('mountet ohne Crash', async () => {
    const w = await mountView(SettingsAuditLogsView, '/settings/audit-logs')
    expect(w.exists()).toBe(true)
  })

  it('rendert Breadcrumb "Audit Logs"', async () => {
    const w = await mountView(SettingsAuditLogsView, '/settings/audit-logs')
    const shell = w.findComponent({ name: 'AppShell' })
    const crumbs = shell.props('breadcrumbs') as Array<{ label: string }>
    expect(crumbs.map((c) => c.label)).toContain('Audit Logs')
  })

  it('zeigt Stub-Hinweis auf Slice G', async () => {
    const w = await mountView(SettingsAuditLogsView, '/settings/audit-logs')
    expect(w.text()).toContain('Slice G')
  })
})
