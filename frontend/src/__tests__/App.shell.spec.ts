/**
 * App.vue — zentrale Huelle (#1795, Ticket 4).
 *
 * Prueft:
 * 1. Die Huelle wird einmal um die Ansichten gelegt und beim Wechsel zwischen
 *    Ansichten nicht neu aufgebaut (ein Mount, ein Unmount erst beim Opt-out).
 * 2. meta.layout === 'bare' rendert die Ansicht ohne Huelle.
 * 3. Brotkrumen einer Ansicht landen ueber useShellBreadcrumbs im Shell-Store
 *    und werden beim Verlassen der Ansicht geraeumt.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'
import { defineComponent, h } from 'vue'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { useShellStore } from '@/stores/shell'
import { useShellBreadcrumbs } from '@/composables/useShellBreadcrumbs'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

const shellLifecycle = vi.hoisted(() => ({ mounted: 0, unmounted: 0 }))

vi.mock('@/components/v4/shell/AppShell.vue', async () => {
  const { defineComponent: define, h: render, onBeforeUnmount: beforeUnmount, onMounted: mounted } = await import('vue')
  return {
    default: define({
      name: 'AppShell',
      props: { demoFrame: { type: Boolean, default: true } },
      setup(_props, { slots }) {
        mounted(() => {
          shellLifecycle.mounted += 1
        })
        beforeUnmount(() => {
          shellLifecycle.unmounted += 1
        })
        return () => render('div', { class: 'shell-stub' }, [render('main', slots.default?.())])
      },
    }),
  }
})
vi.mock('@/components/LogDrawer.vue', () => ({
  default: { name: 'LogDrawer', props: ['open'], template: '<div class="log-drawer-stub" />' },
}))

import App from '../App.vue'

const ViewA = defineComponent({
  name: 'ViewA',
  setup() {
    useShellBreadcrumbs([{ label: 'Ansicht A' }])
    return () => h('section', { class: 'view-a' }, 'A')
  },
})
const ViewB = defineComponent({
  name: 'ViewB',
  // Eine Ansicht ohne eigene Brotkrumen setzt nichts.
  setup: () => () => h('section', { class: 'view-b' }, 'B'),
})
const ViewBare = defineComponent({
  name: 'ViewBare',
  setup: () => () => h('section', { class: 'view-bare' }, 'Bare'),
})

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/a', name: 'A', component: ViewA },
      { path: '/b', name: 'B', component: ViewB },
      { path: '/bare', name: 'Bare', component: ViewBare, meta: { layout: 'bare' } },
    ],
  })
}

async function mountApp() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = makeRouter()
  await router.push('/a')
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [router, pinia, i18n] } })
  await flushPromises()
  return { wrapper, router }
}

/** Die Fade-Transition (out-in) laeuft mit Timern — Ansichtswechsel abwarten. */
async function navigate(router: ReturnType<typeof makeRouter>, path: string) {
  await router.push(path)
  await vi.waitFor(() => {
    expect(router.currentRoute.value.path).toBe(path)
  })
  await new Promise((resolve) => setTimeout(resolve, 600))
  await flushPromises()
}

describe('App.vue — zentrale Huelle', () => {
  beforeEach(() => {
    shellLifecycle.mounted = 0
    shellLifecycle.unmounted = 0
  })

  it('legt die Huelle einmal um die Ansicht', async () => {
    const { wrapper } = await mountApp()
    expect(wrapper.findAll('.shell-stub')).toHaveLength(1)
    expect(wrapper.find('.shell-stub .view-a').exists()).toBe(true)
  })

  it('baut die Huelle beim Wechsel zwischen Ansichten nicht neu auf', async () => {
    const { wrapper, router } = await mountApp()
    const shellBefore = wrapper.find('.shell-stub').element

    await navigate(router, '/b')

    expect(wrapper.find('.view-b').exists()).toBe(true)
    expect(wrapper.find('.view-a').exists()).toBe(false)
    expect(wrapper.find('.shell-stub').element).toBe(shellBefore)
    expect(shellLifecycle.mounted).toBe(1)
    expect(shellLifecycle.unmounted).toBe(0)
  })

  it('rendert Ansichten mit meta.layout "bare" ohne Huelle', async () => {
    const { wrapper, router } = await mountApp()

    await navigate(router, '/bare')

    expect(wrapper.find('.view-bare').exists()).toBe(true)
    expect(wrapper.find('.shell-stub').exists()).toBe(false)
  })

  it('uebergibt Brotkrumen ueber den Shell-Store und raeumt sie beim Verlassen', async () => {
    const { router } = await mountApp()
    const shell = useShellStore()
    expect(shell.breadcrumbs).toEqual([{ label: 'Ansicht A' }])

    await navigate(router, '/b')

    expect(shell.breadcrumbs).toEqual([])
  })
})
