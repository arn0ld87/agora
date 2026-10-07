<script setup lang="ts">
/**
 * Bericht als Reiter am Lauf (Etappe 5, #1804, Bauplan 4.6/6.1):
 * `/simulations/:simulationId/report/:reportId?`. Ohne `reportId` die jüngste
 * Fassung, `new` (Sentinel) bzw. kein Bericht: Start anbieten.
 *
 * Query: `?claim=<claim_id>` (gewählter Claim), `?section=<n>` (Abschnitt),
 * `?panel=evidence|questions` (rechte Spalte). Die Ansicht hält die Adresse und
 * den Zustand in `useRunReport` gleich; die drei Bereiche (Gliederung, Lesetext,
 * Seitenspalte) lesen den Zustand aus `useRunReportContext()`.
 *
 * Lauf ohne Graphen: Berichte stützen sich auf Belege aus dem Graphen, deshalb
 * erklärt der Reiter das und bietet keinen Start an. Das ist kein Fehler. Nur
 * wenn es auch keine Fassung gibt: existiert ein Bericht, bleibt er lesbar.
 */
import { computed, inject, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import ReportAgentChat from '@/components/run/report/ReportAgentChat.vue'
import ReportExportMenu from'@/components/run/report/ReportExportMenu.vue'
import ReportHeader from '@/components/run/report/ReportHeader.vue'
import ReportIncompleteBanner from '@/components/run/report/ReportIncompleteBanner.vue'
import ReportOutlinePane from '@/components/run/report/ReportOutlinePane.vue'
import ReportReadingPane from '@/components/run/report/ReportReadingPane.vue'
import ReportSidePane, { type SidePanel } from '@/components/run/report/ReportSidePane.vue'
import { RUN_WORKSPACE_KEY } from '@/composables/run/useRunWorkspace'
import { provideRunReport, useRunReport } from '@/composables/run/report/useRunReport'
import { buildRunReportRoute } from '@/utils/reportRoute'

const props = defineProps<{ simulationId: string; reportId?: string }>()
const { t, te } = useI18n()
const route = useRoute()
const router = useRouter()
const workspace = inject(RUN_WORKSPACE_KEY, null)

function queryString(key: string): string | null {
  const raw = route.query[key]
  const value = Array.isArray(raw) ? raw[0] : raw
  return typeof value === 'string' && value.length > 0 ? value : null
}

function carriedQuery(): Record<string, string> {
  const panel = queryString('panel')
  return panel ? { panel } : {}
}

const ctx = useRunReport({
  simulationId: () => props.simulationId,
  reportId: () => props.reportId,
  t: (key) => t(key),
  te: (key) => te(key),
  onStarted: (reportId) => {
    void router.replace(buildRunReportRoute({ simulationId: props.simulationId, reportId, query: carriedQuery() }))
  },
})
provideRunReport(ctx)

onMounted(() => void ctx.reload())
watch(
  () => props.simulationId,
  () => void ctx.reload(),
)

// Eine laufende oder fertige Erzeugung ohne Adresse (Start offen): auf deren Bericht wechseln.
watch(
  () => ctx.generation.report.lastStatus.value?.report_id,
  (id) => {
    if (!id || ctx.selectedReportId.value) return
    void router.replace(buildRunReportRoute({ simulationId: props.simulationId, reportId: id, query: carriedQuery() }))
  },
)

function setQuery(patch: Record<string, string | null>): void {
  const next: Record<string, string> = {}
  for (const [k, v] of Object.entries(route.query)) {
    const value = Array.isArray(v) ? v[0] : v
    if (typeof value === 'string') next[k] = value
  }
  for (const [k, v] of Object.entries(patch)) {
    if (v === null) delete next[k]
    else next[k] = v
  }
  void router.replace({ query: next })
}

const activeSection = computed<number | null>(() => {
  const n = Number.parseInt(queryString('section') ?? '', 10)
  return Number.isInteger(n) && n >= 1 ? n : null
})
const panel = computed<SidePanel>(() => (queryString('panel') === 'questions' ? 'questions' : 'evidence'))

watch(
  () => queryString('claim'),
  (claim) => {
    if (claim !== ctx.selectedClaimId.value) ctx.selectClaim(claim)
  },
  { immediate: true },
)
watch(ctx.selectedClaimId, (claim) => {
  if (claim !== queryString('claim')) setQuery({ claim })
})

const reportData = computed(() => (ctx.report.value.status === 'ok' ? ctx.report.value.report : null))
const noGraph = computed(
  () =>
    workspace?.data.value?.hasGraph === false &&
    ctx.versions.value.status === 'ok' &&
    ctx.versions.value.items.length === 0,
)
</script>

<template>
  <section class="run-report" :aria-label="t('views.run.report.label')" data-testid="run-report">
    <p v-if="noGraph" class="run-report__nograph" data-testid="report-no-graph">
      {{ t('views.run.report.noGraph') }}
    </p>

    <template v-else>
      <ReportHeader :simulation-id="simulationId">
        <template #actions><ReportExportMenu /></template>
      </ReportHeader>
      <ReportIncompleteBanner :report="reportData" />

      <div class="run-report__grid" data-testid="report-grid">
        <div class="run-report__col run-report__col--outline">
          <ReportOutlinePane :active-section="activeSection" @select="(n) => setQuery({ section: String(n) })" />
        </div>
        <div class="run-report__col run-report__col--reading">
          <ReportReadingPane :active-section="activeSection" />
        </div>
        <div class="run-report__col run-report__col--side">
          <ReportSidePane :panel="panel" @update:panel="(value) => setQuery({ panel: value })">
            <template #questions><ReportAgentChat :simulation-id="simulationId" /></template>
          </ReportSidePane>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.run-report {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.run-report__nograph {
  margin: 0;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg2);
  font-size: 14px;
  line-height: 1.5;
}
.run-report__grid {
  display: grid;
  grid-template-columns: minmax(170px, 220px) minmax(0, 1fr) minmax(240px, 320px);
  gap: 20px;
  align-items: start;
}
.run-report__col {
  min-width: 0;
}
@media (max-width: 1023px) {
  .run-report__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
