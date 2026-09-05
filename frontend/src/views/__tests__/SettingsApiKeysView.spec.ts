/**
 * SettingsApiKeysView — Smoke-Tests (Slice G2).
 *
 * Prüft:
 *  1. View mountet ohne Crash.
 *  2. PageHeader erhält lokalisierten Titel.
 *  3. Sektionsliste (SettingsOverlay) markiert "API-Schlüssel" als aktiv.
 *  4. "Schlüssel anlegen"-Button ist sichtbar.
 *  5. i18n-Keys lösen auf (kein "settings.v4.apiKeys.*"-Rohdot im DOM).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { makeTestRouter } from '@/components/v4/shell/__tests__/testRouter'

import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'

// localStorage-Mock
const localStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach((k) => delete store[k]) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

// Mock API-Modul — kein echtes HTTP
vi.mock('@/api/apiKeys', () => ({
  listApiKeys: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  createApiKey: vi.fn(),
  revokeApiKey: vi.fn(),
}))

// Shell-Stubs (identisch mit SettingsSubViews.spec.ts)
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

import SettingsApiKeysView from '../Settings/SettingsApiKeysView.vue'

function makeI18n(locale = 'de') {
  return createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'en',
    messages: { de, en },
  })
}

async function mountView() {
  const router = makeTestRouter()
  const pinia = createPinia()
  setActivePinia(pinia)
  const i18n = makeI18n()
  await router.push('/settings/api-keys')
  await router.isReady()
  const wrapper = mount(SettingsApiKeysView, {
    global: { plugins: [router, pinia, i18n] },
  })
  await flushPromises()
  return wrapper
}

describe('SettingsApiKeysView (Slice G2)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('Test 1: mountet ohne Crash', async () => {
    const w = await mountView()
    expect(w.exists()).toBe(true)
  })

  it('Test 2: PageHeader erhält lokalisierten Titel', async () => {
    const w = await mountView()
    const header = w.findComponent({ name: 'PageHeader' })
    expect(header.exists()).toBe(true)
    expect(header.props('title')).toBe('API-Schlüssel')
  })

  it('Test 3: Sektionsliste (SettingsOverlay) markiert "API-Schlüssel" als aktiv', async () => {
    const w = await mountView()
    const active = w.find('a[aria-current="page"]')
    expect(active.exists()).toBe(true)
    expect(active.text()).toBe('API-Schlüssel')
  })

  it('Test 4: "Schlüssel anlegen"-Button ist sichtbar', async () => {
    const w = await mountView()
    const buttons = w.findAll('button')
    const createBtn = buttons.find((b) => b.text().includes('Schlüssel anlegen'))
    expect(createBtn).toBeDefined()
  })

  it('Test 5: keine ungepatchten i18n-Rohkeys im DOM', async () => {
    const w = await mountView()
    expect(w.text()).not.toMatch(/settings\.v4\.apiKeys\./)
  })
})
