import { defineComponent, h, ref, type Component } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { createI18n } from 'vue-i18n'
import { vi } from 'vitest'
import de from '@/i18n/locales/de.json'
import { provideRunReport, useRunReport, type RunReportContext } from '@/composables/run/report/useRunReport'
import { evidenceMap, listEnvelope, reportData } from '@/composables/run/report/__tests__/reportFixtures'

export const Stub = defineComponent({ render: () => h('div', { 'data-testid': 'stub' }) })

export function okApi(over: Record<string, unknown> = {}) {
  const completed = reportData()
  const older = reportData({ report_id: 'report_0', created_at: '2026-10-01T00:00:00Z', completed_at: '2026-10-01T00:30:00Z' })
  return {
    listReports: vi.fn().mockResolvedValue(listEnvelope([older, completed])),
    getReport: vi.fn(async (id: string) => ({ success: true, data: id === 'report_0' ? older : completed })),
    getReportEvidence: vi.fn(async (id: string) => ({ success: true, data: evidenceMap(id) })),
    ...over,
  }
}

export function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/simulations/:simulationId/report/:reportId?', name: 'RunReport', component: Stub },
      { path: '/library/runs', name: 'LibraryRuns', component: Stub },
    ],
  })
}

export const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'de', messages: { de } as never })

/**
 * Hängt eine Komponente unter einen echten `useRunReport`-Kontext (Fake-API) und lädt ihn.
 * `route` ist der Pfad der Memory-History; `reportId` die Adresskomponente.
 */
export async function mountWithReport(
  component: Component,
  props: Record<string, unknown>,
  opts: {
    api?: Record<string, unknown>
    route?: string
    reportId?: string
    load?: boolean
    slots?: Record<string, () => unknown>
  } = {},
) {
  const router = makeRouter()
  await router.push(opts.route ?? '/simulations/sim_1/report')
  await router.isReady()
  const routed = ref<string | undefined>(opts.reportId)
  let ctx!: RunReportContext
  const generationApi = {
    getReportStatus: vi.fn().mockResolvedValue({ success: false }),
    getReport: vi.fn().mockResolvedValue({ success: false }),
    generateReport: vi.fn(),
  }
  const Host = defineComponent({
    setup() {
      ctx = useRunReport({
        simulationId: () => 'sim_1',
        reportId: () => routed.value,
        t: (k) => k,
        api: (opts.api ?? okApi()) as never,
        generationApi: generationApi as never,
      })
      provideRunReport(ctx)
      return () => h(component, props, opts.slots)
    },
  })
  const wrapper = mount(Host, { global: { plugins: [router, i18n], stubs: { RunReportRegenerate: true } } })
  if (opts.load !== false) {
    await ctx.reload()
    await flushPromises()
  }
  return { wrapper, ctx, router, routed, generationApi }
}

export { RouterView }
