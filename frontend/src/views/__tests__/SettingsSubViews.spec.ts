/**
 * SettingsSubViews — Smoke-Tests fuer die v4-Settings-Routen (Slice G1).
 *
 * - General + Integrations sind in Slice G1 real: sie binden
 *   `SettingsSectionPanel` mit gefilterten `allowedSections` ein.
 *   Hier wird SettingsSectionPanel als Stub gemockt, damit der Test
 *   nicht den echten settingsStore + Network-Pfad anlernt.
 * - API Keys / Users & Teams / Audit Logs benutzen den neuen
 *   `ComingSoonCard`-Empty-State.
 */
import { describe, expect, it, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { makeTestRouter } from '@/components/v4/shell/__tests__/testRouter'
import { SettingsSectionSchema } from '@/contracts/settingsContract'
import {
  getActiveLlmConfig,
  setActiveLlmConfig,
} from '@/api/llmRouting'

import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import {
  GENERAL_SETTINGS_SECTIONS,
  INTEGRATION_SETTINGS_SECTIONS,
} from '../Settings/settingsSections'

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
    template: '<div class="page-header-stub"><h1>{{ title }}</h1><p>{{ subtitle }}</p></div>',
  },
}))
vi.mock('@/components/v4/forms/SettingsSectionPanel.vue', () => ({
  default: {
    name: 'SettingsSectionPanel',
    props: ['allowedSections'],
    template: '<div class="section-panel-stub" :data-sections="allowedSections.join(\',\')" />',
  },
}))
vi.mock('@/components/v4/forms/ComingSoonCard.vue', () => ({
  default: {
    name: 'ComingSoonCard',
    props: ['title', 'description'],
    template: '<div class="coming-soon-stub"><h3>{{ title }}</h3><p>{{ description }}</p></div>',
  },
}))
vi.mock('@/components/v4/forms/LlmProfileManager.vue', () => ({
  default: {
    name: 'LlmProfileManager',
    template: '<div class="llm-profile-manager-stub" />',
  },
}))
vi.mock('@/components/v4/forms/AiModelPicker.vue', () => ({
  default: {
    name: 'AiModelPicker',
    props: ['id', 'modelValue'],
    template: '<div class="ai-model-picker-stub" :data-id="id" />',
  },
}))
vi.mock('@/api/llmRouting', () => ({
  listLlmProviders: vi.fn().mockResolvedValue([
    { id: 'ollama', label: 'Ollama' },
    { id: 'openai', label: 'OpenAI' },
  ]),
  listProviderModels: vi.fn().mockImplementation(async (providerId: string) => (
    providerId === 'openai'
      ? [{ id: 'gpt-4o-mini', label: 'GPT-4o mini' }]
      : [{ id: 'qwen3', label: 'Qwen 3' }]
  )),
  getActiveLlmConfig: vi.fn().mockResolvedValue({ provider_id: 'ollama', model: 'qwen3' }),
  setActiveLlmConfig: vi.fn().mockResolvedValue({ provider_id: 'openai', model: 'gpt-4o-mini' }),
}))

import SettingsGeneralView from '../Settings/SettingsGeneralView.vue'
import SettingsIntegrationsView from '../Settings/SettingsIntegrationsView.vue'
import SettingsUsersTeamsView from '../Settings/SettingsUsersTeamsView.vue'
import SettingsApiKeysView from '../Settings/SettingsApiKeysView.vue'
import SettingsAuditLogsView from '../Settings/SettingsAuditLogsView.vue'

function makeI18n(locale = 'de') {
  return createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'en',
    messages: { de, en },
  })
}

async function mountView(component: object, path: string) {
  const router = makeTestRouter()
  const pinia = createPinia()
  setActivePinia(pinia)
  const i18n = makeI18n()
  await router.push(path)
  await router.isReady()
  const wrapper = mount(component, {
    global: { plugins: [router, pinia, i18n] },
  })
  await flushPromises()
  return wrapper
}

describe('Settings-Section-Parität (Slice 7.4a)', () => {
  it('ordnet jede Schema-Section exakt einer v4-Settings-Seite zu', () => {
    const mappedSections = [
      ...GENERAL_SETTINGS_SECTIONS,
      ...INTEGRATION_SETTINGS_SECTIONS,
    ]
    const occurrences = mappedSections.reduce<Record<string, number>>((counts, section) => {
      counts[section] = (counts[section] ?? 0) + 1
      return counts
    }, {})

    expect(
      Object.entries(occurrences)
        .filter(([, count]) => count !== 1)
        .map(([section]) => section),
    ).toEqual([])
    expect([...new Set(mappedSections)].sort()).toEqual([...SettingsSectionSchema.options].sort())
  })

  it('erhält den separaten active-config-Lade- und Speicherpfad im General-Surface', async () => {
    const w = await mountView(SettingsGeneralView, '/settings/general')

    expect(getActiveLlmConfig).toHaveBeenCalled()
    expect((w.get('#settings-active-provider').element as HTMLSelectElement).value).toBe('ollama')
    expect((w.get('#settings-active-model').element as HTMLSelectElement).value).toBe('qwen3')

    await w.get('#settings-active-provider').setValue('openai')
    await flushPromises()
    await w.get('#settings-active-model').setValue('gpt-4o-mini')
    await w.get('.settings-general__active-save').trigger('click')
    await flushPromises()

    expect(setActiveLlmConfig).toHaveBeenCalledWith({
      provider_id: 'openai',
      model: 'gpt-4o-mini',
    })
  })
})

describe('SettingsGeneralView (Slice G1, real)', () => {
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

  it('rendert PageHeader mit lokalisiertem Titel', async () => {
    const w = await mountView(SettingsGeneralView, '/settings/general')
    expect(w.find('.page-header-stub h1').text()).toBe('Allgemein')
  })

  it('reicht General-Sektionen an SettingsSectionPanel', async () => {
    const w = await mountView(SettingsGeneralView, '/settings/general')
    const panel = w.findComponent({ name: 'SettingsSectionPanel' })
    expect(panel.exists()).toBe(true)
    const allowed = panel.props('allowedSections') as string[]
    expect(allowed).toEqual(GENERAL_SETTINGS_SECTIONS)
  })

  it('zeigt keinen "Slice G folgt"-Stub mehr', async () => {
    const w = await mountView(SettingsGeneralView, '/settings/general')
    expect(w.text()).not.toContain('Slice G')
  })
})

describe('SettingsIntegrationsView (Slice G1, real)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('mountet ohne Crash', async () => {
    const w = await mountView(SettingsIntegrationsView, '/settings/integrations')
    expect(w.exists()).toBe(true)
  })

  it('rendert Breadcrumb "Integrations"', async () => {
    const w = await mountView(SettingsIntegrationsView, '/settings/integrations')
    const shell = w.findComponent({ name: 'AppShell' })
    const crumbs = shell.props('breadcrumbs') as Array<{ label: string }>
    // Locale-agnostisch: deutscher "Integrationen"-String und englischer
    // "Integrations"-String sind beide gueltige Lokalisierungen.
    const labels = crumbs.map((c) => c.label)
    expect(labels.some((l) => /^Integration(en|s)?$/.test(l))).toBe(true)
  })

  it('reicht Integrations-Sektionen an SettingsSectionPanel', async () => {
    const w = await mountView(SettingsIntegrationsView, '/settings/integrations')
    const panel = w.findComponent({ name: 'SettingsSectionPanel' })
    const allowed = panel.props('allowedSections') as string[]
    expect(allowed).toEqual(INTEGRATION_SETTINGS_SECTIONS)
  })
})

// Slice G2: SettingsApiKeysView ist jetzt real — eigene Smoke-Tests in
// views/__tests__/SettingsApiKeysView.spec.ts. Dieser Block prüft nur
// noch, dass kein ComingSoonCard-Stub mehr erscheint.
describe('SettingsApiKeysView (Slice G2, real)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('rendert Breadcrumb "API Keys"', async () => {
    const w = await mountView(SettingsApiKeysView, '/settings/api-keys')
    const shell = w.findComponent({ name: 'AppShell' })
    const crumbs = shell.props('breadcrumbs') as Array<{ label: string }>
    expect(crumbs.map((c) => c.label)).toContain('API Keys')
  })

  it('rendert keine ComingSoonCard mehr (View ist real)', async () => {
    const w = await mountView(SettingsApiKeysView, '/settings/api-keys')
    const card = w.findComponent({ name: 'ComingSoonCard' })
    expect(card.exists()).toBe(false)
  })

  it('zeigt keinen "Slice G folgt"-Stub mehr', async () => {
    const w = await mountView(SettingsApiKeysView, '/settings/api-keys')
    expect(w.text()).not.toContain('Slice G')
  })
})

describe('SettingsUsersTeamsView (Slice G1, coming soon)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('rendert ComingSoonCard mit lokalisiertem Titel', async () => {
    const w = await mountView(SettingsUsersTeamsView, '/settings/users-teams')
    const card = w.findComponent({ name: 'ComingSoonCard' })
    expect(card.exists()).toBe(true)
    expect(card.props('title')).toBe('Multi-User-Verwaltung folgt')
  })
})

describe('SettingsAuditLogsView (Slice G1, coming soon)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('rendert ComingSoonCard mit lokalisiertem Titel', async () => {
    const w = await mountView(SettingsAuditLogsView, '/settings/audit-logs')
    const card = w.findComponent({ name: 'ComingSoonCard' })
    expect(card.exists()).toBe(true)
    expect(card.props('title')).toBe('Audit-Trail folgt')
  })
})
