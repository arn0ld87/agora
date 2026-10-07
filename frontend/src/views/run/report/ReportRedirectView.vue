<script setup lang="ts">
/**
 * Weiterleitung der alten Berichtsadressen `/report/:reportId` und
 * `/v4/report/:reportId` auf `/simulations/:simulationId/report/:reportId`
 * (Etappe 5, #1804, Bauplan 6.2). Die Simulation steht nicht in der alten
 * Adresse: sie kommt aus `?simId=` (nur eine `sim_…`-Kennung), beim Sentinel
 * `new` aus `?simulationId=`, sonst aus `GET /api/report/<id>`. Query (ohne die
 * beiden Hilfsschlüssel) und Hash bleiben erhalten.
 *
 * Lade- und Fehlerzustand sind sichtbar: „Bericht nicht gefunden“ (404) ist
 * etwas anderes als ein Lade- oder Vertragsfehler mit erneutem Versuch.
 */
import { onMounted, ref } from 'vue'
import { useRoute, useRouter, type LocationQueryRaw } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { getReport } from '@/api/report'
import { ApiError } from '@/api/envelope'
import { ReportSchema } from '@/contracts/reportContract'
import { isSimulationId } from '@/contracts/runIdentifiers'
import { INTERACTION_SIMULATION_ID_QUERY_KEY, PENDING_REPORT_ID, REPORT_SIMULATION_ID_QUERY_KEY } from '@/utils/reportRoute'

const props = defineProps<{ reportId: string }>()
const { t } = useI18n()
const route = useRoute()
const router = useRouter()

type ViewState = 'loading' | 'notFound' | 'error'
const state = ref<ViewState>('loading')
const reason = ref<string | null>(null)

function first(value: unknown): string | null {
  const v = Array.isArray(value) ? value[0] : value
  return typeof v === 'string' && v.length > 0 ? v : null
}

function describe(err: unknown): string {
  return err instanceof Error && err.message ? err.message : String(err)
}

async function resolveSimulationId(): Promise<string | null> {
  const hinted = first(route.query[INTERACTION_SIMULATION_ID_QUERY_KEY])
  if (isSimulationId(hinted)) return hinted
  if (props.reportId === PENDING_REPORT_ID) {
    const pending = first(route.query[REPORT_SIMULATION_ID_QUERY_KEY])
    if (isSimulationId(pending)) return pending
    state.value = 'notFound'
    return null
  }
  const res = (await getReport(props.reportId)) as { success?: boolean; data?: unknown; error?: string; code?: string }
  if (!res?.success) {
    if (res?.code === 'not_found') {
      state.value = 'notFound'
    } else {
      state.value = 'error'
      reason.value = res?.error || 'getReport'
    }
    return null
  }
  const parsed = ReportSchema.safeParse(res.data)
  if (!parsed.success) {
    state.value = 'error'
    reason.value = `Vertragsbruch GET /api/report/${props.reportId}: ${parsed.error.message}`
    return null
  }
  return parsed.data.simulation_id
}

async function resolve(): Promise<void> {
  state.value = 'loading'
  reason.value = null
  try {
    const simulationId = await resolveSimulationId()
    if (!simulationId) return
    const query: LocationQueryRaw = { ...route.query }
    delete query[INTERACTION_SIMULATION_ID_QUERY_KEY]
    delete query[REPORT_SIMULATION_ID_QUERY_KEY]
    await router.replace({
      name: 'RunReport',
      params: { simulationId, reportId: props.reportId },
      query,
      hash: route.hash,
    })
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      state.value = 'notFound'
      return
    }
    state.value = 'error'
    reason.value = describe(err)
  }
}

onMounted(() => void resolve())
</script>

<template>
  <div class="report-redirect" data-testid="report-redirect">
    <p v-if="state === 'loading'" class="report-redirect__status" role="status" data-testid="report-redirect-loading">
      {{ t('views.run.report.redirect.loading') }}
    </p>
    <section v-else-if="state === 'notFound'" class="report-redirect__problem" role="alert" data-testid="report-redirect-not-found">
      <h1 class="report-redirect__title">{{ t('views.run.report.redirect.notFoundTitle') }}</h1>
      <p>{{ t('views.run.report.redirect.notFoundBody', { id: reportId }) }}</p>
      <router-link :to="{ name: 'LibraryRuns' }" class="report-redirect__btn">
        {{ t('views.run.report.redirect.toRuns') }}
      </router-link>
    </section>
    <section v-else class="report-redirect__problem" role="alert" data-testid="report-redirect-error">
      <h1 class="report-redirect__title">{{ t('views.run.report.redirect.errorTitle') }}</h1>
      <p>{{ reason }}</p>
      <button type="button" class="report-redirect__btn" data-testid="report-redirect-retry" @click="resolve()">
        {{ t('views.run.report.redirect.retry') }}
      </button>
    </section>
  </div>
</template>

<style scoped>
.report-redirect {
  padding: 24px;
  color: var(--fg);
}
.report-redirect__status {
  margin: 0;
  color: var(--fg2);
}
.report-redirect__problem {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  max-width: 560px;
}
.report-redirect__title {
  margin: 0;
  font-size: 18px;
  font-weight: 650;
}
.report-redirect__btn {
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
}
.report-redirect__btn:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
</style>
