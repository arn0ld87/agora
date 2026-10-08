/**
 * UserMenu (#1617): Legacy-Betreibermenü vs. Supabase-Session mit
 * Workspace-Wechsel und Abmelden.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, reactive } from 'vue'

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(async () => {}) }))
vi.mock('vue-router', () => ({ useRouter: () => router }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('../../../store/userProfile', () => ({ useUserProfileStore: () => ({ profile: null }) }))

const WS_A = { workspace_id: 'aaaaaaaa-0000-4000-8000-000000000001', name: 'Alpha', slug: 'alpha', role: 'owner' }
const WS_B = { workspace_id: 'bbbbbbbb-0000-4000-8000-000000000002', name: 'Beta', slug: 'beta', role: 'viewer' }

const auth = reactive({
  jwtEnabled: false,
  session: null as null | object,
  user: null as null | { email: string },
  workspaces: [] as typeof WS_A[],
  activeWorkspaceId: null as string | null,
  switchWorkspace: vi.fn(async () => {}),
  signOut: vi.fn(async () => {}),
})
vi.mock('../../../store/auth', () => ({ useAuthStore: () => auth }))

// Dropdown ohne Popup-Mechanik: Trigger und Inhalt direkt rendern.
vi.mock('../../v4/forms/DropdownMenu.vue', () => ({
  default: defineComponent({
    setup(_, { slots }) {
      return () => h('div', [slots.trigger?.({ isOpen: true }), slots.default?.({ close: () => {} })])
    },
  }),
}))
vi.mock('../../v4/forms/DropdownMenuItem.vue', () => ({
  default: defineComponent({
    emits: ['select'],
    setup(_, { slots, emit, attrs }) {
      return () => h('button', { role: 'menuitem', ...attrs, onClick: (e: Event) => emit('select', e) }, slots.default?.())
    },
  }),
}))

import UserMenu from '../UserMenu.vue'
import { THEME_STORAGE_KEY, useTheme } from '../../../composables/useTheme'
import { useDensity } from '../../../composables/useDensity'

function items(wrapper: ReturnType<typeof mount>) {
  return wrapper.findAll('[role="menuitem"]').map((b) => b.text())
}

beforeEach(() => {
  Object.assign(auth, {
    jwtEnabled: false,
    session: null,
    user: null,
    workspaces: [],
    activeWorkspaceId: null,
  })
  auth.switchWorkspace.mockClear()
  auth.signOut.mockClear()
  router.replace.mockClear()
})

describe('UserMenu', () => {
  it('routes the legacy profile item through the operator access section', async () => {
    const wrapper = mount(UserMenu)
    const profile = wrapper.findAll('[role="menuitem"]').find((item) => item.text() === 'topbar.userMenu.profile')
    await profile?.trigger('click')
    expect(router.push).toHaveBeenCalledWith({ name: 'SettingsWindow', params: { section: 'access' } })
  })
  it('offers profile access with a session', async () => {
    Object.assign(auth, { jwtEnabled: true, session: { access_token: 'x' }, user: { email: 'user@example.test' } })
    const wrapper = mount(UserMenu)
    const profile = wrapper.findAll('[role="menuitem"]').find((item) => item.text() === 'topbar.userMenu.profile')
    expect(profile).toBeDefined()
    await profile?.trigger('click')
    expect(router.push).toHaveBeenCalledWith({ name: 'SettingsWindow', params: { section: 'profile' } })
  })

  it('zeigt im Legacy-Modus das Betreibermenü ohne Abmelden', () => {
    const wrapper = mount(UserMenu)

    expect(items(wrapper)).toEqual([
      'topbar.userMenu.profile',
      'topbar.userMenu.settings',
      'topbar.userMenu.help',
    ])
  })

  it('zeigt mit Session die Workspaces, markiert den aktiven und blendet Betreiberpunkte aus', () => {
    Object.assign(auth, {
      jwtEnabled: true,
      session: { access_token: 'x' },
      user: { email: 'alice@example.test' },
      workspaces: [WS_A, WS_B],
      activeWorkspaceId: WS_A.workspace_id,
    })
    const wrapper = mount(UserMenu)

    expect(wrapper.text()).toContain('alice@example.test')
    expect(wrapper.find('[data-testid="user-menu-workspace-alpha"]').attributes('aria-current')).toBe('true')
    expect(wrapper.find('[data-testid="user-menu-workspace-beta"]').attributes('aria-current')).toBeUndefined()
    expect(items(wrapper).join('|')).not.toContain('topbar.userMenu.settings')
    expect(wrapper.find('[data-testid="user-menu-sign-out"]').exists()).toBe(true)
  })

  it('wechselt nur zu einem anderen Workspace', async () => {
    Object.assign(auth, {
      jwtEnabled: true,
      session: { access_token: 'x' },
      workspaces: [WS_A, WS_B],
      activeWorkspaceId: WS_A.workspace_id,
    })
    const wrapper = mount(UserMenu)

    await wrapper.find('[data-testid="user-menu-workspace-alpha"]').trigger('click')
    expect(auth.switchWorkspace).not.toHaveBeenCalled()

    await wrapper.find('[data-testid="user-menu-workspace-beta"]').trigger('click')
    expect(auth.switchWorkspace).toHaveBeenCalledWith(WS_B.workspace_id)
  })

  it('Darstellung: Theme-Wahl System/Hell/Dunkel als Radio-Eintraege ueber useTheme()', async () => {
    useTheme._resetForTesting()
    localStorage.removeItem(THEME_STORAGE_KEY)
    const wrapper = mount(UserMenu)

    const radios = wrapper.findAll('[role="menuitemradio"]')
    expect(radios.map((r) => r.attributes('data-testid'))).toEqual([
      'user-menu-theme-system',
      'user-menu-theme-light',
      'user-menu-theme-dark',
    ])
    expect(wrapper.find('[data-testid="user-menu-theme-system"]').attributes('aria-checked')).toBe('true')

    await wrapper.find('[data-testid="user-menu-theme-dark"]').trigger('click')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(wrapper.find('[data-testid="user-menu-theme-dark"]').attributes('aria-checked')).toBe('true')

    await wrapper.find('[data-testid="user-menu-theme-light"]').trigger('click')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
  })

  it('Darstellung: Dichte bleibt als Schalter im Menue erreichbar', async () => {
    const { density, setDensity } = useDensity()
    setDensity('comfortable')
    const wrapper = mount(UserMenu)
    const item = wrapper.find('[data-testid="user-menu-density"]')
    expect(item.attributes('role')).toBe('menuitemcheckbox')
    expect(item.attributes('aria-checked')).toBe('false')

    await item.trigger('click')
    expect(density.value).toBe('compact')
    expect(wrapper.find('[data-testid="user-menu-density"]').attributes('aria-checked')).toBe('true')
    setDensity('comfortable')
  })

  it('zeigt im Legacy-Modus einen reinen Workspace-Anzeigeeintrag, mit Session nicht', () => {
    const legacy = mount(UserMenu)
    expect(legacy.find('[data-testid="user-menu-workspace-local"]').exists()).toBe(true)
    expect(items(legacy).join('|')).not.toContain('workspaceLocal')

    Object.assign(auth, { jwtEnabled: true, session: { access_token: 'x' } })
    expect(mount(UserMenu).find('[data-testid="user-menu-workspace-local"]').exists()).toBe(false)
  })

  it('meldet ab und geht zum Login', async () => {
    Object.assign(auth, { jwtEnabled: true, session: { access_token: 'x' } })
    const wrapper = mount(UserMenu)

    await wrapper.find('[data-testid="user-menu-sign-out"]').trigger('click')
    await flushPromises()

    expect(auth.signOut).toHaveBeenCalledTimes(1)
    expect(router.replace).toHaveBeenCalledWith({ name: 'Login' })
  })
})
