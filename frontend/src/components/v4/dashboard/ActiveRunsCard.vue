<script setup lang="ts">
/**
 * ActiveRunsCard — Active-Runs-Liste über useRunsPolling.
 *
 * Workbench-These: kompakte Tabelle, Mono für IDs/Project-Slugs, Phase als
 * Tone-Pill (graph_build=teal, simulation_prepare=purple, simulation_run=blue,
 * report_generate=orange).
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Card from '../forms/Card.vue'
import Badge from '../forms/Badge.vue'
import DataTable, { type DataTableColumn } from '../data/DataTable.vue'
import EmptyState from '../data/EmptyState.vue'
import type { RunDetail } from '../../../contracts/runsContract'

const props = defineProps<{
  runs: RunDetail[]
  loading: boolean
  error: string
}>()

const emit = defineEmits<{
  refresh: []
}>()

const { t } = useI18n()
const router = useRouter()

const ACTIVE_STATUSES = ['pending', 'processing', 'paused'] as const

const activeRuns = computed<RunDetail[]>(() =>
  props.runs.filter(r => (ACTIVE_STATUSES as readonly string[]).includes(r.status))
    .slice(0, 8),
)

const columns: DataTableColumn[] = [
  { key: 'run_id', label: t('dashboard.active.columns.runId'), mono: true, width: '180px' },
  { key: 'project', label: t('dashboard.active.columns.project'), secondary: true },
  { key: 'phase', label: t('dashboard.active.columns.phase'), width: '180px' },
  { key: 'progress', label: t('dashboard.active.columns.progress'), align: 'right', width: '90px' },
  { key: 'started', label: t('dashboard.active.columns.started'), secondary: true, align: 'right', width: '120px' },
]

const PHASE_TONE: Record<string, 'teal' | 'purple' | 'blue' | 'orange' | 'gray'> = {
  graph_build: 'teal',
  simulation_prepare: 'purple',
  simulation_run: 'blue',
  report_generate: 'orange',
}

function phaseLabel(runType: string): string {
  const key = `dashboard.active.phase.${runType}`
  const fallback = runType
  const translated = t(key)
  return translated === key ? fallback : translated
}

function phaseTone(runType: string) {
  return PHASE_TONE[runType] ?? 'gray'
}

function shortId(id: string): string {
  if (id.length <= 12) return id
  return `${id.slice(0, 8)}…${id.slice(-3)}`
}

function relTime(iso: string): string {
  const ts = Date.parse(iso)
  if (Number.isNaN(ts)) return '—'
  // clamp gegen Clock-Skew — Server-Timestamp kann minimal in der Zukunft liegen
  const diff = Math.max(0, Date.now() - ts)
  const secs = Math.round(diff / 1000)
  if (secs < 60) return t('dashboard.time.secondsAgo', { n: secs })
  const mins = Math.round(secs / 60)
  if (mins < 60) return t('dashboard.time.minutesAgo', { n: mins })
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return t('dashboard.time.hoursAgo', { n: hrs })
  return new Date(ts).toLocaleDateString()
}

interface Row extends Record<string, unknown> {
  id: string
  run_id: string
  run_id_display: string
  project: string
  phase: string
  phase_tone: 'teal' | 'purple' | 'blue' | 'orange' | 'gray'
  progress: number
  started: string
  raw: RunDetail
}

const rows = computed<Row[]>(() =>
  activeRuns.value.map(r => ({
    id: r.run_id,
    run_id: r.run_id,
    run_id_display: shortId(r.run_id),
    project: r.summary?.document_name ?? r.linked_ids?.project_id as string ?? r.entity_id,
    phase: phaseLabel(r.run_type),
    phase_tone: phaseTone(r.run_type),
    progress: r.progress ?? 0,
    started: relTime(r.started_at),
    raw: r,
  })),
)

function openRun(row: Row) {
  router.push({ name: 'RunDetail', params: { id: row.run_id } })
}
</script>

<template>
  <Card :title="$t('dashboard.active.title')">
    <template #right>
      <span v-if="loading && rows.length === 0" class="ar-loading">{{ $t('common.loading') }}</span>
      <Badge v-else-if="rows.length > 0" tone="blue" :dot="false">{{ rows.length }}</Badge>
    </template>

    <div v-if="error" class="ar-error">
      <Badge tone="red">{{ $t('dashboard.active.errorLabel') }}</Badge>
      <span class="ar-error__msg">{{ error }}</span>
      <button class="ar-retry v4-state-interactive" type="button" @click="emit('refresh')">
        {{ $t('common.tryAgain') }}
      </button>
    </div>

    <template v-else-if="rows.length === 0">
      <EmptyState
        :title="$t('dashboard.active.emptyTitle')"
        :subtitle="$t('dashboard.active.emptyHint')"
      />
    </template>

    <DataTable
      v-else
      :columns="columns"
      :rows="rows"
      :row-click="openRun"
      compact
    >
      <template #cell-run_id="{ row }">
        <span class="ar-id">{{ (row as Row).run_id_display }}</span>
      </template>
      <template #cell-phase="{ row }">
        <Badge :tone="(row as Row).phase_tone">{{ (row as Row).phase }}</Badge>
      </template>
      <template #cell-progress="{ row }">
        <span class="ar-progress">{{ (row as Row).progress }}<span class="ar-progress__unit">%</span></span>
      </template>
    </DataTable>
  </Card>
</template>

<style scoped>
.ar-loading {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--text-tertiary);
}

.ar-error {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.ar-error__msg {
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-secondary);
  flex: 1;
  min-width: 0;
}

.ar-retry {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--accent);
  /* v4-state-interactive liefert background/border/transition/hover/focus-ring/cursor */
  border-radius: var(--r-3, 6px);
  padding: 4px 8px;
  /* Override: accent-tint-bg statt default hover-bg */
  --v4-state-hover-bg: var(--accent-tint-bg);
}

.ar-id {
  font-family: var(--font-mono);
  font-size: 12.5px;
  color: var(--text-primary);
}

.ar-progress {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text-primary);
}

.ar-progress__unit {
  color: var(--text-tertiary);
}
</style>
