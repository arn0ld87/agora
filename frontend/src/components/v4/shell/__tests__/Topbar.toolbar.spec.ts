/**
 * Topbar — Werkzeugleiste (#1795, Ticket 7): Symbolknopf der Suche ab
 * 1024 px, Fehlerplakette der Konsole, "Neuer Lauf".
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick, type Ref } from 'vue'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { ShellTestId } from '@/contracts/testIds'
import { makeTestRouter } from './testRouter'

vi.mock('@/composables/useLogDrawer', async () => {
  const { ref } = await import('vue')
  const unread = ref(0)
  const isOpen = ref(false)
  const available = ref(true)
  return {
    useLogDrawer: () => ({
      isOpen,
      unreadErrors: unread,
      available,
      toggle: () => {
        isOpen.value = !isOpen.value
      },
    }),
    __state: { unread, isOpen, available },
  }
})

import * as drawerModule from '@/composables/useLogDrawer'
import Topbar from '../Topbar.vue'

const state = (drawerModule as unknown as {
  __state: { unread: Ref<number>; isOpen: Ref<boolean>; available: Ref<boolean> }
}).__state

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })
const router = makeTestRouter()

function mountTopbar() {
  return mount(Topbar, {
    global: { plugins: [router, createPinia(), i18n], stubs: { Breadcrumbs: true, Icon: true } },
  })
}

function mockMatchMedia(matches: boolean): void {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: (query: string) => ({
      matches,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  })
}

describe('Topbar Werkzeugleiste', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    state.unread.value = 0
    state.isOpen.value = false
    state.available.value = true
    document.body.innerHTML = ''
  })

  afterEach(() => {
    Reflect.deleteProperty(window, 'matchMedia')
  })

  it('zeigt die Suche breit mit Beschriftung und Kuerzel', async () => {
    mockMatchMedia(false)
    const trigger = mountTopbar().find(`[data-testid="${ShellTestId.cmdkTrigger}"]`)
    expect(trigger.text()).toContain('Suche')
    expect(trigger.find('.kbd').text()).toBe('⌘K')
  })

  it('wird bei 1024 px abwaerts zum Symbolknopf mit zugaenglichem Namen', async () => {
    mockMatchMedia(true)
    const trigger = mountTopbar().find(`[data-testid="${ShellTestId.cmdkTrigger}"]`)
    expect(trigger.exists()).toBe(true)
    expect(trigger.text()).toBe('')
    expect(trigger.find('.kbd').exists()).toBe(false)
    expect(trigger.attributes('aria-label')).toBe('Suchen (Cmd+K)')
  })

  it('Konsolen-Plakette: bei 0 unsichtbar, ab 1 sichtbar mit Zahl im Namen', async () => {
    mockMatchMedia(false)
    const wrapper = mountTopbar()
    expect(wrapper.find('[data-testid="topbar-console-badge"]').exists()).toBe(false)
    const button = wrapper.find(`[data-testid="${ShellTestId.logsTrigger}"]`)
    expect(button.attributes('aria-label')).toBe('Konsole ein- oder ausblenden')

    state.unread.value = 3
    await nextTick()
    const badge = wrapper.find('[data-testid="topbar-console-badge"]')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toBe('3')
    expect(button.attributes('aria-label')).toContain('3 ungelesene Fehler')
  })

  it('Konsolen-Knopf schaltet die Konsole und spiegelt den Zustand in aria-pressed', async () => {
    mockMatchMedia(false)
    const wrapper = mountTopbar()
    const button = wrapper.find(`[data-testid="${ShellTestId.logsTrigger}"]`)
    expect(button.attributes('aria-pressed')).toBe('false')
    await button.trigger('click')
    expect(state.isOpen.value).toBe(true)
    expect(button.attributes('aria-pressed')).toBe('true')
  })

  it('Konsolen-Knopf fehlt ohne Betreiberzugang', async () => {
    mockMatchMedia(false)
    state.available.value = false
    expect(mountTopbar().find(`[data-testid="${ShellTestId.logsTrigger}"]`).exists()).toBe(false)
  })

  it('"Neuer Lauf" fuehrt zum bestehenden Start (NewRun mit HeroNewRun)', async () => {
    mockMatchMedia(false)
    await router.push('/library/runs')
    const wrapper = mountTopbar()
    const button = wrapper.find('[data-testid="topbar-new-run"]')
    expect(button.text()).toContain('Neuer Lauf')
    await button.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('NewRun')
  })
})
