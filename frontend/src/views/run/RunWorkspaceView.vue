<script setup lang="ts">
/**
 * Lauf-Arbeitsbereich (Etappe 2, #1797, Bauplan 4.2/6.2): Lauf-Kopf mit der
 * Frage als Titel und der Zustandsmarke, sechs Reiter, darunter die
 * Kind-Ansicht. Lädt die Daten des Laufs einmal initial und reicht sie per
 * `provide` an die Übersicht weiter; solange eine Stufe`queued`/`running`/
 * `paused` ist, lädt der Arbeitsbereich stillos per `usePolling` nach
 * (UAT-006) und stoppt bei Terminalzustand.
 */
import { computed, onMounted, provide, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import RunTabs from '@/components/run/RunTabs.vue'
import RunStateMark from '@/components/run/RunStateMark.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import { usePolling } from '@/composables/usePolling'
import { crumbForId, useShellBreadcrumbs } from '@/composables/useShellBreadcrumbs'
import { POLLING_STAGE_STATES } from '@/composables/run/runStageState'
import { RUN_WORKSPACE_KEY, RUN_WORKSPACE_POLL_INTERVAL_MS, useRunWorkspace } from '@/composables/run/useRunWorkspace'

const props = defineProps<{ simulationId: string }>()
const { t } = useI18n()

const ws = useRunWorkspace(() => props.simulationId)
provide(RUN_WORKSPACE_KEY, ws)

onMounted(() => void ws.reload())
watch(
  () => props.simulationId,
  () => void ws.reload(),
)

// Still-Refresh der Übersicht (UAT-006): läuft eine Stufe, holt der
// Arbeitsbereich periodisch nach; terminal Stufen beenden das Polling.
const polling = usePolling(() => ws.reload(true), RUN_WORKSPACE_POLL_INTERVAL_MS)
const isPollingStage = computed(() => ws.stages.value.some((r) => POLLING_STAGE_STATES.has(r.state)))
watch(isPollingStage, (active) => {
  if (active) void polling.start()
  else polling.stop()
})

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: t('views.library.title'), path: '/library/runs' },
  { label: t('views.library.runs.title'), path: '/library/runs' },
  crumbForId(props.simulationId),
])
useShellBreadcrumbs(crumbs)

const headline = computed(() => {
  const h = ws.headline.value
  return h ? h : null
})
</script>

<template>
  <div class="run-workspace" data-testid="run-workspace">
    <p v-if="ws.state.value === 'loading'" class="run-workspace__status" role="status" data-testid="run-loading">
      {{ t('views.run.header.loading') }}
    </p>

    <section
      v-else-if="ws.state.value === 'notFound'"
      class="run-workspace__problem"
      role="alert"
      data-testid="run-not-found"
    >
      <h1 class="run-workspace__problem-title">{{ t('views.run.header.notFoundTitle') }}</h1>
      <p>{{ t('views.run.header.notFoundBody', { id: simulationId }) }}</p>
      <router-link :to="{ name: 'LibraryRuns' }" class="run-workspace__btn">
        {{ t('views.run.header.toRuns') }}
      </router-link>
    </section>

    <section
      v-else-if="ws.state.value === 'error'"
      class="run-workspace__problem run-workspace__problem--error"
      role="alert"
      data-testid="run-error"
    >
      <h1 class="run-workspace__problem-title">{{ t('views.run.header.errorTitle') }}</h1>
      <p class="run-workspace__detail">{{ ws.error.value }}</p>
      <button type="button" class="run-workspace__btn" data-testid="run-retry" @click="ws.reload()">
        {{ t('views.run.header.retry') }}
      </button>
    </section>

    <template v-else>
      <header class="run-workspace__head">
        <h1
          class="run-workspace__title"
          :class="{ 'run-workspace__title--missing': !ws.question.value }"
          data-testid="run-title"
        >
          {{ ws.question.value ?? t('views.run.header.questionMissing') }}
        </h1>
        <div v-if="headline" class="run-workspace__state" data-testid="run-headline">
          <span class="run-workspace__state-stage">{{ t(`views.run.stage.${headline.stage}`) }}</span>
          <RunStateMark :state="headline.state" />
        </div>
      </header>
      <RunTabs :tabs="ws.tabs.value" />
      <router-view />
    </template>
  </div>
</template>

<style scoped>
.run-workspace {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.run-workspace__status {
  color: var(--fg2);
  font-size: 14px;
}
.run-workspace__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  margin: 0 0 14px;
}
.run-workspace__title {
  flex: 1 1 280px;
  min-width: 0;
  margin: 0;
  max-width: 980px;
  font-size: 21px;
  line-height: 1.38;
  font-weight: 650;
  letter-spacing: -0.005em;
  text-wrap: pretty;
  color: var(--fg);
}
.run-workspace__title--missing {
  color: var(--fg2);
  font-weight: 500;
}
.run-workspace__state {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
  font-size: 12.5px;
  color: var(--fg2);
}
.run-workspace__problem {
  max-width: 560px;
  padding: 20px 24px;
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg);
}
.run-workspace__problem--error {
  border: 1px solid var(--err);
}
.run-workspace__problem-title {
  margin: 0 0 8px;
  font-size: 18px;
}
.run-workspace__detail {
  font-family: var(--ag-font-mono);
  font-size: 12.5px;
  color: var(--fg2);
  overflow-wrap: anywhere;
}
.run-workspace__btn {
  display: inline-flex;
  align-items: center;
  height: 34px;
  padding: 0 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 13.5px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
}
.run-workspace__btn:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
</style>
