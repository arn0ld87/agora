<script setup lang="ts">
/**
 * Aktivität → Jobs (Etappe 2, Ticket 5, #1797): alle Jobs der RunRegistry mit
 * Art, Lauf, Zustand, Fortschritt und Dauer. Die Liste kommt wie in der
 * Ablage aus `GET /api/runs` und wird über `useRunsPolling` aktualisiert
 * (Polling plus Realtime-Signal, keine zweite Dauerverbindung).
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import ActivityTabs from '@/components/activity/ActivityTabs.vue'
import JobsTable from '@/components/activity/JobsTable.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import { useShellBreadcrumbs } from '@/composables/useShellBreadcrumbs'
import { useRunsPolling } from '@/composables/useRunsPolling'
import { cancelRun } from '@/api/runs'
import { filterJobRows, JOB_STATES, jobRowsOf, type JobState } from '@/composables/activity/jobState'

const { t, te } = useI18n()

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: t('views.activity.title'), path: '/activity/jobs' },
  { label: t('views.activity.jobs.title') },
])
useShellBreadcrumbs(crumbs)

const { runs, loading, error, start, stop, refresh } = useRunsPolling()
const loaded = ref(false)
const now = ref(Date.now())
watch(runs, () => { now.value = Date.now() })
watch(loading, (isLoading, wasLoading) => { if (wasLoading && !isLoading) loaded.value = true })

onMounted(() => { void start() })
onBeforeUnmount(() => { stop() })

const kindFilter = ref('')
const stateFilter = ref<JobState | ''>('')

const rows = computed(() => jobRowsOf(runs.value, now.value))
const kinds = computed(() => [...new Set(rows.value.map((r) => r.runType))].sort())
const visible = computed(() => filterJobRows(rows.value, { kind: kindFilter.value, state: stateFilter.value }))
const filtered = computed(() => !!kindFilter.value || !!stateFilter.value)

function kindLabel(runType: string): string {
  return te(`views.activity.jobs.kind.${runType}`) ? t(`views.activity.jobs.kind.${runType}`) : runType
}

function resetFilters(): void {
  kindFilter.value = ''
  stateFilter.value = ''
}

const notice = ref('')
const noticeIsError = ref(false)

async function onCancel(runId: string): Promise<void> {
  try {
    await cancelRun(runId)
    notice.value = t('views.activity.jobs.action.cancelRequested')
    noticeIsError.value = false
  } catch (e) {
    notice.value = `${t('views.activity.jobs.action.cancelFailed')}: ${e instanceof Error ? e.message : String(e)}`
    noticeIsError.value = true
  }
  void refresh()
}
</script>

<template>
  <section class="activity-jobs">
    <PageHeader :title="t('views.activity.title')" />
    <ActivityTabs />

    <div class="filters">
      <label class="filter">
        <span>{{ t('views.activity.jobs.filter.kind') }}</span>
        <select v-model="kindFilter" data-test="filter-kind">
          <option value="">{{ t('views.activity.jobs.filter.all') }}</option>
          <option v-for="k in kinds" :key="k" :value="k">{{ kindLabel(k) }}</option>
        </select>
      </label>
      <label class="filter">
        <span>{{ t('views.activity.jobs.filter.state') }}</span>
        <select v-model="stateFilter" data-test="filter-state">
          <option value="">{{ t('views.activity.jobs.filter.all') }}</option>
          <option v-for="s in JOB_STATES" :key="s" :value="s">{{ t(`views.activity.jobs.state.${s}`) }}</option>
        </select>
      </label>
    </div>

    <p v-if="notice" class="notice" :class="{ 'is-error': noticeIsError }" role="status" aria-live="polite">{{ notice }}</p>
    <p v-if="error" class="state is-error" role="alert" data-test="error">{{ t('views.activity.jobs.error', { message: error }) }}</p>

    <p v-if="!loaded && !runs.length && !error" class="state" role="status" data-test="loading">{{ t('views.activity.jobs.loading') }}</p>
    <JobsTable v-else-if="visible.length" :rows="visible" @cancel="onCancel" />
    <p v-else-if="loaded && !error" class="state" data-test="empty">
      {{ filtered ? t('views.activity.jobs.emptyFiltered') : t('views.activity.jobs.empty') }}
      <button v-if="filtered" type="button" class="reset" @click="resetFilters">{{ t('views.activity.jobs.filter.none') }}</button>
    </p>
  </section>
</template>

<style scoped>
.activity-jobs { display: flex; flex-direction: column; min-height: 0; }
.filters { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 14px; }
.filter { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; color: var(--fg2); }
.filter select {
  height: 32px; padding: 0 10px; border: none; border-radius: var(--ag-r-8);
  background: var(--field); color: var(--fg); font: inherit; font-size: 13px;
}
.filter select:focus-visible, .reset:focus-visible { outline: 2px solid var(--acc); outline-offset: 1px; }
.state { color: var(--fg2); font-size: 13.5px; padding: 12px 0; margin: 0; }
.state.is-error, .notice.is-error { color: var(--err); }
.notice { margin: 0 0 10px; font-size: 13px; color: var(--fg2); }
.reset {
  margin-left: 8px; height: 28px; padding: 0 10px; border: none; border-radius: var(--ag-r-8);
  background: var(--s3); color: var(--fg); font: inherit; font-size: 12.5px; cursor: pointer;
}
</style>
