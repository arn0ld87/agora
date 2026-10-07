import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: { value: 'de' } }),
}))

const auth = vi.hoisted(() => ({ isAuthenticated: true }))
vi.mock('@/store/auth', () => ({ useAuthStore: () => auth }))

const api = vi.hoisted(() => ({ list: vi.fn() }))
vi.mock('@/api/apiKeys', () => ({
  listApiKeys: api.list,
  createApiKey: vi.fn(),
  revokeApiKey: vi.fn(),
}))

import SectionAccess from '../../sections/SectionAccess.vue'
import SettingsApiKeysView from '@/views/Settings/SettingsApiKeysView.vue'
import SettingsAuditLogsView from '@/views/Settings/SettingsAuditLogsView.vue'

const PanelStub = defineComponent({
  name: 'SettingsSectionPanel',
  props: { allowedSections: { type: Array, required: true } },
  template: '<div data-testid="security-stub" />',
})
const ProfileStub = defineComponent({
  name: 'SettingsProfileView',
  props: { embedded: { type: Boolean, default: false } },
  template: '<div data-testid="profile-stub" />',
})

const KEY = {
  id: 'k1',
  label: 'CI',
  prefix: 'ago_0123abcd',
  scopes: ['read'],
  status: 'active',
  hashed_token: 'HASHED-SECRET-VALUE',
  created_at: '2026-10-01T10:00:00Z',
  last_used_at: null,
  revoked_at: null,
}

function mountAccess() {
  return mount(SectionAccess, {
    global: {
      stubs: { SettingsSectionPanel: PanelStub, SettingsProfileView: ProfileStub, ComingSoonCard: true },
    },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  auth.isAuthenticated = true
  api.list.mockReset().mockResolvedValue({ items: [KEY], total: 1 })
})

describe('SectionAccess', () => {
  it('zeigt vier Gruppen mit h3 und ohne h1/h2', async () => {
    const wrapper = mountAccess()
    await flushPromises()
    const titles = wrapper.findAll('h3.section-access__title').map((h) => h.text())
    expect(titles).toEqual([
      'views.settingsWindow.access.apiKeys',
      'views.settingsWindow.access.audit',
      'views.settingsWindow.access.account',
      'views.settingsWindow.access.security',
    ])
    expect(wrapper.find('h1').exists()).toBe(false)
    expect(wrapper.findComponent(SettingsApiKeysView).props('embedded')).toBe(true)
    expect(wrapper.findComponent(SettingsAuditLogsView).props('embedded')).toBe(true)
    expect(wrapper.findComponent(ProfileStub).props('embedded')).toBe(true)
    expect(wrapper.findComponent(PanelStub).props('allowedSections')).toEqual(['security'])
    expect(wrapper.text()).not.toContain('placeholderTitle')
  })

  it('zeigt Schlüssel nur mit Präfix, nie Hash oder Klartext', async () => {
    const wrapper = mountAccess()
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('ago_0123abcd')
    expect(text).not.toContain('HASHED-SECRET-VALUE')
    expect(wrapper.html()).not.toMatch(/ago_[0-9a-f]{48}/)
  })

  it('Schlüsseltabelle liegt in einem fokussierbaren, beschrifteten Wrapper', async () => {
    const wrapper = mountAccess()
    await flushPromises()
    const wrap = wrapper.get('.api-keys__table-wrap')
    expect(wrap.attributes('tabindex')).toBe('0')
    expect(wrap.attributes('aria-label')).toBeTruthy()
  })

  it('ohne Token/Sitzung: Konto und Sicherheit bleiben, Schlüssel und Audit nicht', async () => {
    auth.isAuthenticated = false
    const wrapper = mountAccess()
    await flushPromises()
    expect(wrapper.findComponent(SettingsApiKeysView).exists()).toBe(false)
    expect(wrapper.findComponent(SettingsAuditLogsView).exists()).toBe(false)
    expect(api.list).not.toHaveBeenCalled()
    expect(wrapper.findAll('[role="status"]')).toHaveLength(2)
    expect(wrapper.find('[data-testid="profile-stub"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="security-stub"]').exists()).toBe(true)
  })

  it('Altrouten ohne embedded zeigen weiter ihren Seitenkopf', () => {
    const wrapper = mount(SettingsAuditLogsView, {
      global: { stubs: { ComingSoonCard: true } },
    })
    expect(wrapper.findAll('h1')).toHaveLength(1)
    const embedded = mount(SettingsAuditLogsView, {
      props: { embedded: true },
      global: { stubs: { ComingSoonCard: true } },
    })
    expect(embedded.find('h1').exists()).toBe(false)
  })
})
