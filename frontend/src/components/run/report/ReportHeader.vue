<script setup lang="ts">
/**
 * Kopf des Bericht-Reiters (Etappe 5, #1804, Bauplan 4.6): Fassungswähler,
 * Zustand der gewählten Fassung, „Neu erzeugen mit …“ und ein Platz für das
 * Export-Menü (Slot `actions`, füllt ein anderes Ticket).
 *
 * Die Frage des Laufs steht im Kopf des Arbeitsbereichs, nicht hier. Ein
 * Modell je Fassung nennt der Bericht-Vertrag nicht; deshalb steht keines da.
 * Ein Wechsel der Fassung ändert die Adresse (`/simulations/:id/report/:reportId`);
 * `?panel=` bleibt, Claim und Abschnitt der alten Fassung entfallen.
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import RunReportRegenerate from '@/components/run/RunReportRegenerate.vue'
import RunStateMark from '@/components/run/RunStateMark.vue'
import { reportStateKind } from '@/composables/run/runStageState'
import { useRunReportContext } from '@/composables/run/report/useRunReport'
import { formatShelfDate } from '@/composables/useShelf'
import { buildRunReportRoute } from '@/utils/reportRoute'

const props = defineProps<{ simulationId: string }>()
const { t, locale } = useI18n()
const router = useRouter()
const route = useRoute()
const ctx = useRunReportContext()

const items = computed(() => (ctx.versions.value.status === 'ok' ? ctx.versions.value.items : []))
const selected = computed(() => items.value.find((v) => v.reportId === ctx.selectedReportId.value) ?? null)
const selectedStatus = computed<string | null>(() => {
  const rep = ctx.report.value
  if (rep.status === 'ok' && rep.report.report_id === ctx.selectedReportId.value) return rep.report.status
  return selected.value?.status ?? null
})
const selectedState = computed(() => (selectedStatus.value ? reportStateKind(selectedStatus.value) : null))

function optionLabel(v: { number: number; createdAt: string; status: string }): string {
  return t('views.run.report.header.versionOption', {
    n: v.number,
    date: formatShelfDate(v.createdAt, locale.value, t),
    state: t(`views.run.state.${reportStateKind(v.status)}`),
  })
}

function carriedQuery(): Record<string, string> {
  const panel = route.query.panel
  return typeof panel === 'string' ? { panel } : {}
}

async function open(reportId: string): Promise<void> {
  await router.push(buildRunReportRoute({ simulationId: props.simulationId, reportId, query: carriedQuery() }))
}

function onPick(event: Event): void {
  const id = (event.target as HTMLSelectElement).value
  if (id && id !== ctx.selectedReportId.value) void open(id)
}

/** Neue Fassung angelegt: Liste neu laden und auf die jüngste wechseln. */
async function onRegenerated(): Promise<void> {
  await ctx.reload()
  const latest = items.value[0]
  if (latest && latest.reportId !== ctx.selectedReportId.value) await open(latest.reportId)
}

const versionsFailure = computed(() => (ctx.versions.value.status === 'failed' ? ctx.versions.value.reason : null))
const invalid = computed(() => (ctx.versions.value.status === 'ok' ? ctx.versions.value.invalid : 0))
</script>

<template>
  <header class="rr-head" data-testid="report-header">
    <div class="rr-head__row">
      <div class="rr-head__field">
        <label class="rr-head__label" for="report-version-select">{{ t('views.run.report.header.versionLabel') }}</label>
        <select
          v-if="items.length > 0"
          id="report-version-select"
          class="rr-head__select"
          :value="ctx.selectedReportId.value ?? ''"
          data-testid="report-version-select"
          @change="onPick"
        >
          <option v-for="v in items" :key="v.reportId" :value="v.reportId">{{ optionLabel(v) }}</option>
        </select>
        <span v-else-if="ctx.versions.value.status === 'loading'" class="rr-head__note" data-testid="report-versions-loading">
          {{ t('views.run.report.header.versionsLoading') }}
        </span>
        <span v-else class="rr-head__note" data-testid="report-versions-none">{{ t('views.run.report.header.noVersions') }}</span>
      </div>

      <div v-if="selectedState" class="rr-head__field" data-testid="report-state">
        <span class="rr-head__label">{{ t('views.run.report.header.stateLabel') }}</span>
        <RunStateMark :state="selectedState" />
      </div>

      <div class="rr-head__actions">
        <RunReportRegenerate :simulation-id="simulationId" @done="onRegenerated" />
        <slot name="actions" />
      </div>
    </div>

    <p v-if="versionsFailure" class="rr-head__problem" role="alert" data-testid="report-versions-failed">
      {{ t('views.run.report.header.versionsFailed', { reason: versionsFailure }) }}
    </p>
    <p v-if="invalid > 0" class="rr-head__problem" role="status" data-testid="report-versions-invalid">
      {{ t('views.run.report.header.versionsInvalid', { n: invalid }, invalid) }}
    </p>
  </header>
</template>

<style scoped>
.rr-head {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.rr-head__row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 16px;
}
.rr-head__field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.rr-head__label {
  font-size: 12px;
  font-weight: 600;
  color: var(--fg3);
}
.rr-head__select {
  height: 32px;
  max-width: 100%;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s2);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
}
.rr-head__select:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.rr-head__note {
  font-size: 13px;
  color: var(--fg2);
}
.rr-head__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
.rr-head__actions :deep(.run-regen__trigger) {
  margin-top: 0;
}
.rr-head__problem {
  margin: 0;
  font-size: 13px;
  color: var(--fg);
}
</style>
