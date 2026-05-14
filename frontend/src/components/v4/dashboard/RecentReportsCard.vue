<script setup lang="ts">
/**
 * RecentReportsCard — letzte abgeschlossene Reports.
 *
 * Datenquelle: listRuns({ run_type:'report_generate', status:'completed', limit:8 })
 * eigenständig gepollt (alle 30 s — weniger volatil als ActiveRuns).
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Card from '../forms/Card.vue'
import Badge from '../forms/Badge.vue'
import DataTable, { type DataTableColumn } from '../data/DataTable.vue'
import EmptyState from '../data/EmptyState.vue'
import { listRuns } from '../../../api/runs'
import { ApiError } from '../../../api/envelope'
import { RunDetailSchema, type RunDetail } from '../../../contracts/runsContract'
import { usePolling } from '../../../composables/usePolling'

const { t } = useI18n()
const router = useRouter()

const reports = ref<RunDetail[]>([])
const loading = ref(false)
const error = ref('')

async function tick(): Promise<void> {
  loading.value = true
  try {
    const envelope = await listRuns({
      run_type: 'report_generate',
      status: 'completed',
      limit: 8,
    })
    const payload = (envelope as { data?: { runs?: unknown[] } }).data
    const rawRuns = payload?.runs ?? []
    const parsed: RunDetail[] = []
    for (const item of rawRuns) {
      const ok = RunDetailSchema.safeParse(item)
      if (ok.success) parsed.push(ok.data)
    }
    reports.value = parsed
    error.value = ''
  } catch (e) {
    if (e instanceof ApiError) error.value = e.message
    else error.value = e instanceof Error ? e.message : t('errors.network')
  } finally {
    loading.value = false
  }
}

const polling = usePolling(tick, 30000, { pauseWhenHidden: true })

onMounted(() => void polling.start({ immediate: true }))
onUnmounted(() => polling.stop())

const columns: DataTableColumn[] = [
  { key: 'report_id', label: t('dashboard.reports.columns.reportId'), mono: true, width: '180px' },
  { key: 'project', label: t('dashboard.reports.columns.project'), secondary: true },
  { key: 'personas', label: t('dashboard.reports.columns.personas'), mono: true, align: 'right', width: '100px' },
  { key: 'confidence', label: t('dashboard.reports.columns.confidence'), align: 'right', width: '120px' },
  { key: 'date', label: t('dashboard.reports.columns.date'), secondary: true, align: 'right', width: '120px' },
]

interface ReportRow extends Record<string, unknown> {
  id: string
  report_id_display: string
  report_id_full: string | null
  project: string
  personas: number | null
  confidence: number | null
  date: string
  raw: RunDetail
}

function shortId(id: string | null | undefined): string {
  if (!id) return '—'
  if (id.length <= 12) return id
  return `${id.slice(0, 8)}…${id.slice(-3)}`
}

function fmtDate(iso?: string | null): string {
  if (!iso) return '—'
  const ts = Date.parse(iso)
  if (Number.isNaN(ts)) return '—'
  return new Date(ts).toLocaleDateString()
}

function pickConfidence(r: RunDetail): number | null {
  const meta = r.metadata as Record<string, unknown>
  const cand = meta?.['confidence_score'] ?? meta?.['confidence']
  if (typeof cand === 'number' && Number.isFinite(cand)) return cand
  return null
}

const rows = computed<ReportRow[]>(() =>
  reports.value.map(r => {
    const linked = r.linked_ids as Record<string, unknown>
    const reportId = typeof linked?.['report_id'] === 'string' ? (linked['report_id'] as string) : null
    return {
      id: r.run_id,
      report_id_display: shortId(reportId ?? r.run_id),
      report_id_full: reportId,
      project: r.summary?.document_name ?? r.entity_id,
      personas: r.summary?.persona_count ?? null,
      confidence: pickConfidence(r),
      date: fmtDate(r.completed_at ?? r.updated_at),
      raw: r,
    }
  }),
)

function openReport(row: ReportRow) {
  if (row.report_id_full) {
    router.push({ name: 'Report', params: { reportId: row.report_id_full } })
  } else {
    router.push({ name: 'RunDetail', params: { id: row.raw.run_id } })
  }
}

function confidenceTone(c: number | null): 'green' | 'orange' | 'red' | 'gray' {
  if (c === null) return 'gray'
  if (c >= 0.7) return 'green'
  if (c >= 0.45) return 'orange'
  return 'red'
}
</script>

<template>
  <Card :title="$t('dashboard.reports.title')">
    <template #right>
      <span v-if="loading && rows.length === 0" class="rr-loading">{{ $t('common.loading') }}</span>
      <Badge v-else-if="rows.length > 0" tone="blue" :dot="false">{{ rows.length }}</Badge>
    </template>

    <div v-if="error" class="rr-error">
      <Badge tone="red">{{ $t('dashboard.active.errorLabel') }}</Badge>
      <span class="rr-error__msg">{{ error }}</span>
      <button class="rr-retry" type="button" @click="() => void polling.tick()">
        {{ $t('common.tryAgain') }}
      </button>
    </div>

    <template v-else-if="rows.length === 0">
      <EmptyState
        :title="$t('dashboard.reports.emptyTitle')"
        :subtitle="$t('dashboard.reports.emptyHint')"
      />
    </template>

    <DataTable
      v-else
      :columns="columns"
      :rows="rows"
      :row-click="openReport"
      compact
    >
      <template #cell-report_id="{ row }">
        <span class="rr-id">{{ (row as ReportRow).report_id_display }}</span>
      </template>
      <template #cell-personas="{ row }">
        <template v-if="(row as ReportRow).personas !== null">{{ (row as ReportRow).personas }}</template>
        <span v-else class="rr-dim">—</span>
      </template>
      <template #cell-confidence="{ row }">
        <template v-if="(row as ReportRow).confidence !== null">
          <Badge :tone="confidenceTone((row as ReportRow).confidence)">
            {{ Math.round(((row as ReportRow).confidence as number) * 100) }}%
          </Badge>
        </template>
        <span v-else class="rr-dim">—</span>
      </template>
    </DataTable>
  </Card>
</template>

<style scoped>
.rr-loading {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--text-tertiary);
}

.rr-error {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.rr-error__msg {
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-secondary);
  flex: 1;
  min-width: 0;
}

.rr-retry {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--accent);
  background: transparent;
  border: 0;
  padding: 4px 8px;
  cursor: pointer;
  border-radius: var(--r-3, 6px);
}

.rr-retry:hover {
  background: var(--accent-tint-bg);
}

.rr-retry:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--focus-ring);
}

.rr-dim {
  color: var(--text-quaternary);
}

.rr-id {
  font-family: var(--font-mono);
  font-size: 12.5px;
  color: var(--text-primary);
}
</style>
