<script setup lang="ts">
/**
 * Lauf → Übersicht (Etappe 2, #1797, Bauplan 4.2): ersetzt den Stepper. Eine
 * Zeile je Stufe, darunter Budgetstand, Frage, Graph und Personasatz. Die
 * Daten liefert der Arbeitsbereich; hier wird nur dargestellt.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import RunStageTable from '@/components/run/RunStageTable.vue'
import RunResourceMonitor from '@/components/v4/run-budget/RunResourceMonitor.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import { TerminationReasonSchema } from '@/contracts/runBudgetContract'
import { crumbForId, useShellBreadcrumbs } from '@/composables/useShellBreadcrumbs'
import { useRunWorkspaceContext } from '@/composables/run/useRunWorkspace'

const props = defineProps<{ simulationId?: string }>()
const { t } = useI18n()
const ws = useRunWorkspaceContext()

const simulationId = computed(() => ws.data.value?.simulationId ?? props.simulationId ?? '')

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: t('views.library.title'), path: '/library/runs' },
  { label: t('views.library.runs.title'), path: '/library/runs' },
  crumbForId(simulationId.value),
])
useShellBreadcrumbs(crumbs)

const rows = computed(() => ws.stages.value)
const hasReport = computed(() => (ws.data.value?.reports.length ?? 0) > 0)
const personasRow = computed(() => rows.value.find((r) => r.key === 'personas') ?? null)
const graphRow = computed(() => rows.value.find((r) => r.key === 'graph') ?? null)

const budgetTermination = computed(() => {
  const parsed = TerminationReasonSchema.safeParse(ws.budgetJob.value?.terminationReason)
  return parsed.success ? parsed.data : null
})
</script>

<template>
  <div class="run-overview" data-testid="run-overview">
    <h2 class="run-overview__sr-title">{{ t('views.run.overview.title') }}</h2>

    <RunStageTable :rows="rows" :has-report="hasReport" />

    <section class="run-overview__budget" aria-labelledby="run-budget-title" data-testid="run-budget">
      <h3 id="run-budget-title" class="run-overview__h">{{ t('views.run.overview.budgetTitle') }}</h3>
      <RunResourceMonitor
        v-if="ws.budgetJob.value"
        :run-id="ws.budgetJob.value.runId"
        :status="ws.budgetJob.value.status"
        :termination-reason="budgetTermination"
      />
      <p v-else class="run-overview__missing" data-testid="run-budget-missing">
        {{ t('views.run.overview.budgetNone') }}
      </p>
    </section>

    <section class="run-overview__cards" :aria-label="t('views.run.overview.cardsLabel')">
      <article class="run-card" data-testid="card-question">
        <h3 class="run-overview__h">{{ t('views.run.overview.questionTitle') }}</h3>
        <p v-if="ws.question.value" class="run-card__text">{{ ws.question.value }}</p>
        <p v-else class="run-overview__missing">{{ t('views.run.overview.questionMissing') }}</p>
      </article>

      <article class="run-card" data-testid="card-graph">
        <h3 class="run-overview__h">{{ t('views.run.overview.graphTitle') }}</h3>
        <p v-if="ws.graphName.value && graphRow && graphRow.state !== 'notStarted'" class="run-card__text">
          {{ ws.graphName.value }}
        </p>
        <p v-else class="run-overview__missing">{{ t('views.run.overview.graphMissing') }}</p>
        <router-link
          :to="{ name: 'RunGraph', params: { simulationId } }"
          class="run-card__link"
          data-testid="card-graph-link"
        >
          {{ t('views.run.overview.openGraph') }}
        </router-link>
      </article>

      <article class="run-card" data-testid="card-personas">
        <h3 class="run-overview__h">{{ t('views.run.overview.personasTitle') }}</h3>
        <p v-if="ws.personaCount.value !== null" class="run-card__text">
          {{ t('views.run.overview.personasCount', { n: ws.personaCount.value }) }}
        </p>
        <p v-else class="run-overview__missing">{{ t('views.run.overview.personasMissing') }}</p>
        <router-link
          v-if="personasRow?.next.to"
          :to="personasRow.next.to"
          class="run-card__link"
          data-testid="card-personas-link"
        >
          {{ t('views.run.overview.openPersonas') }}
        </router-link>
      </article>
    </section>
  </div>
</template>

<style scoped>
.run-overview {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
.run-overview__sr-title {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
.run-overview__h {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--fg2);
}
.run-overview__missing {
  margin: 0;
  font-size: 13px;
  color: var(--fg3);
}
.run-overview__cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
}
.run-card {
  padding: 16px 18px;
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg);
}
.run-card__text {
  margin: 0 0 10px;
  font-size: 14px;
  line-height: 1.45;
  text-wrap: pretty;
}
.run-card__link {
  font-size: 13px;
  font-weight: 600;
  color: var(--acc-text);
}
.run-card__link:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
</style>
