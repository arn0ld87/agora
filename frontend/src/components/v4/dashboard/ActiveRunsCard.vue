<script setup lang="ts">
/**
 * ActiveRunsCard — Active-Runs-Liste über useRunsPolling.
 *
 * Workbench-These: kompakte Tabelle, Mono für IDs/Project-Slugs, Phase als
 * Tone-Pill (graph_build=teal, simulation_prepare=purple, simulation_run=blue,
 * report_generate=orange).
 *
 * Phase 3: Globaler Kill-Switch pro Run. Nutzt stopRun(runId) aus api/runs
 * (generischer Run-Registry-Stop, key=run_id) — nicht stopSimulation, da auf
 * der Übersicht Runs aller Phasen (graph_build/report_generate) stehen, die
 * keine simulation_id tragen. Bestätigungsdialog via vue-i18n, optimistisches
 * Loading-State, danach emit('refresh') für sofortigen Re-Poll der Liste.
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Card from '../forms/Card.vue'
import Badge from '../forms/Badge.vue'
import Button from '../forms/Button.vue'
import DataTable, { type DataTableColumn } from '../data/DataTable.vue'
import EmptyState from '../data/EmptyState.vue'
import { stopRun } from '@/api/runs'
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

// Optimistische Stop-States: run_ids, deren Stop-Aufruf aussteht.
const stoppingIds = ref<Set<string>>(new Set())
const stopError = ref('')

const columns: DataTableColumn[] = [
  { key: 'run_id', label: t('dashboard.active.columns.runId'), mono: true, width: '180px' },
  { key: 'project', label: t('dashboard.active.columns.project'), secondary: true },
  { key: 'phase', label: t('dashboard.active.columns.phase'), width: '180px' },
  { key: 'progress', label: t('dashboard.active.columns.progress'), align: 'right', width: '90px' },
  { key: 'started', label: t('dashboard.active.columns.started'), secondary: true, mono: true, align: 'right', width: '120px' },
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

function isStopping(runId: string): boolean {
  return stoppingIds.value.has(runId)
}

// Nur Simulation-Runs unterstützen den generischen Stop (Backend returnt 409
// für andere run_types — s. backend test_runs_resume_stop.py:
// test_resume_unsupported_run_type_returns_409). graph_build/report_generate
// haben keinen killbaren Hintergrund-Task; ein Stop-Call würde immer failen.
const STOPPABLE_RUN_TYPE = 'simulation_run'
function canStopRun(runType: string): boolean {
  return runType === STOPPABLE_RUN_TYPE
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

async function doStop(row: Row) {
  if (isStopping(row.run_id)) return
  if (typeof window !== 'undefined' && !window.confirm(t('dashboard.active.stopConfirm'))) return
  stoppingIds.value = new Set(stoppingIds.value).add(row.run_id)
  stopError.value = ''
  try {
    await stopRun(row.run_id)
    // Sofortigen Re-Poll triggern — Parent (DashboardView::useRunsPolling)
    // aktualisiert die Liste; der nächste 5s-Tick und ein ggf. offener
    // Step3-Wizard (eigenes Polling) ziehen den neuen Status nach.
    emit('refresh')
    // stoppingIds bewusst NICHT hier clearen: der Button bleibt disabled,
    // bis der Parent refreshed props liefert und die Row aus activeRuns
    // verschwindet (status → stopped). Verhindert doppelte Stop-Requests
    // im Gap zwischen stopRun-Resolve und dem nächsten Polling-Tick.
    // CodeRabbit Minor (F3).
  } catch (err) {
    stopError.value = t('dashboard.active.stopError', {
      message: err instanceof Error ? err.message : String(err),
    })
    // Bei Fehler freigeben, damit der User retryen kann.
    const next = new Set(stoppingIds.value)
    next.delete(row.run_id)
    stoppingIds.value = next
  }
}

// Stale stopping-Flags abräumen, sobald die betroffene Run die aktive Menge
// verlässt (status → stopped/completed/failed). Wird durch den Parent-Re-Poll
// nach emit('refresh') gespeist. CodeRabbit Minor (F3).
//
// Wichtig: auf `props.runs` (ungefiltert) schauen, NICHT auf `activeRuns` —
// letzteres ist für die Tabelle auf 8 Rows gecappt, sonst würden bei >8
// aktiven Runs die stoppingIds der Rows 9+ vorzeitig gecleart (CodeRabbit
// 21:53Z Re-Review). Die aktive Menge wird hier ohne Cap aus ACTIVE_STATUSES
// bestimmt.
watch(() => props.runs, (runs) => {
  if (stoppingIds.value.size === 0) return
  const activeIds = new Set(
    runs
      .filter(r => (ACTIVE_STATUSES as readonly string[]).includes(r.status))
      .map(r => r.run_id),
  )
  const next = new Set(stoppingIds.value)
  for (const id of stoppingIds.value) {
    if (!activeIds.has(id)) next.delete(id)
  }
  if (next.size !== stoppingIds.value.size) stoppingIds.value = next
}, { deep: true })
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

    <template v-else>
      <div v-if="stopError" class="ar-stoperror">
        <Badge tone="red">{{ $t('dashboard.active.errorLabel') }}</Badge>
        <span class="ar-stoperror__msg">{{ stopError }}</span>
      </div>

      <EmptyState
        v-if="rows.length === 0"
        :title="$t('dashboard.active.emptyTitle')"
        :subtitle="$t('dashboard.active.emptyHint')"
      />

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
      <template #actions="{ row }">
        <Button
          v-if="canStopRun((row as Row).raw.run_type)"
          class="ar-stop"
          variant="danger"
          size="sm"
          icon
          :aria-label="$t('dashboard.active.stopLabel')"
          :loading="isStopping((row as Row).run_id)"
          :disabled="isStopping((row as Row).run_id)"
          @click.stop="doStop(row as Row)"
        />
      </template>
    </DataTable>
    </template>
  </Card>
</template>

<style scoped>
.ar-loading {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--text-tertiary);
}

.ar-error,
.ar-stoperror {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.ar-error__msg,
.ar-stoperror__msg {
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

/* Stop-Button in der Actions-Spalte — darf den Row-Klick nicht triggern. */
.ar-stop {
  /* kleines Target, aber über v4-state-interactive voll fokussierbar */
  --v4-state-hover-bg: var(--status-red-bg);
}
</style>