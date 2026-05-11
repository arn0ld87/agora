<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, toRef } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useRunsPolling } from '../composables/useRunsPolling'
import type { RunDetail } from '../contracts/runsContract'

// ---- Props ----
const props = withDefaults(
  defineProps<{ pollIntervalMs?: number }>(),
  { pollIntervalMs: 5000 },
)

// ---- Setup ----
const { t } = useI18n()
const router = useRouter()

// ---- Polling ----
const { runs, loading, error, isRunning, start, stop, refresh } = useRunsPolling(
  toRef(props, 'pollIntervalMs'),
)

onMounted(() => void start())
onUnmounted(() => stop())

// ---- Filter Pills ----
type FilterKey = 'all' | 'active' | 'done' | 'failed'

const activeFilter = ref<FilterKey>('all')

const STATUS_BUCKETS: Record<FilterKey, string[]> = {
  all: [],
  active: ['pending', 'processing', 'paused'],
  done: ['completed'],
  failed: ['failed', 'stopped'],
}

const FILTER_LABELS: FilterKey[] = ['all', 'active', 'done', 'failed']

// ---- Search ----
const searchQuery = ref('')

// ---- Derived list ----
const filteredRuns = computed<RunDetail[]>(() => {
  let list = runs.value

  // Status filter
  const bucket = STATUS_BUCKETS[activeFilter.value]
  if (bucket.length > 0) {
    list = list.filter((r) => bucket.includes(r.status))
  }

  // Search filter (run_id, entity_id, summary.document_name)
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter(
      (r) =>
        r.run_id.toLowerCase().includes(q) ||
        r.entity_id.toLowerCase().includes(q) ||
        (r.summary?.document_name ?? '').toLowerCase().includes(q),
    )
  }

  return list
})

// ---- Click-through ----
function openDetail(run: RunDetail): void {
  void router.push({ name: 'RunDetail', params: { id: run.run_id } })
}

// ---- Status badge helper ----
function statusClass(status: string): string {
  if (['pending', 'processing', 'paused'].includes(status)) return 'badge--active'
  if (status === 'completed') return 'badge--done'
  return 'badge--failed'
}

function statusIcon(status: string): string {
  if (status === 'pending') return '○'
  if (status === 'processing') return '●'
  if (status === 'paused') return '⏸'
  if (status === 'completed') return '✓'
  return '✕'
}

// ---- Interval display ----
const intervalSeconds = computed(() => Math.round(props.pollIntervalMs / 1000))
</script>

<template>
  <section class="runs-dashboard" aria-label="Runs Dashboard">
    <!-- Header -->
    <header class="dashboard-header">
      <div class="header-title-row">
        <h1 class="dashboard-title">{{ t('runs.dashboard.title') }}</h1>
        <span class="live-indicator" :class="{ 'live-indicator--active': isRunning }">
          {{ t('runs.dashboard.live_label', { interval: intervalSeconds }) }}
        </span>
        <button
          class="refresh-btn"
          type="button"
          :aria-label="t('common.refresh')"
          :disabled="loading"
          @click="() => void refresh()"
        >
          ↻
        </button>
      </div>

      <!-- Filter Pills -->
      <nav class="filter-pills" :aria-label="t('runs.dashboard.columns.status')">
        <button
          v-for="key in FILTER_LABELS"
          :key="key"
          type="button"
          class="pill"
          :class="{ 'pill--active': activeFilter === key }"
          :aria-pressed="activeFilter === key"
          @click="activeFilter = key"
        >
          {{ t(`runs.dashboard.filter.${key}`) }}
        </button>
      </nav>

      <!-- Search -->
      <div class="search-row">
        <input
          v-model="searchQuery"
          type="search"
          class="search-input"
          :placeholder="t('runs.dashboard.search_placeholder')"
          :aria-label="t('runs.dashboard.search_placeholder')"
        />
      </div>
    </header>

    <!-- Error banner -->
    <div v-if="error" class="error-banner" role="alert">
      {{ t('runs.dashboard.error', { message: error }) }}
    </div>

    <!-- Loading state (initial only) -->
    <div v-if="loading && runs.length === 0" class="state-message" aria-live="polite">
      {{ t('runs.dashboard.loading') }}
    </div>

    <!-- Empty state -->
    <div
      v-else-if="!loading && filteredRuns.length === 0"
      class="state-message"
      aria-live="polite"
    >
      {{ t('runs.dashboard.empty') }}
    </div>

    <!-- Runs list -->
    <ul v-else class="runs-list" role="list">
      <li
        v-for="run in filteredRuns"
        :key="run.run_id"
        class="run-row"
        role="listitem"
      >
        <button
          type="button"
          class="run-row-btn"
          :aria-label="`${run.run_type} – ${run.run_id}`"
          @click="openDetail(run)"
        >
          <!-- Status badge -->
          <span class="badge" :class="statusClass(run.status)" :title="run.status">
            {{ statusIcon(run.status) }}
          </span>

          <!-- Run type -->
          <span class="col col--type">{{ run.run_type }}</span>

          <!-- Entity / Document -->
          <span class="col col--entity">
            {{ run.summary?.document_name ?? run.entity_id }}
          </span>

          <!-- Progress -->
          <span class="col col--progress">
            <span class="progress-bar" role="progressbar" :aria-valuenow="run.progress" aria-valuemin="0" aria-valuemax="100">
              <span class="progress-fill" :style="{ width: `${run.progress}%` }" />
            </span>
            <span class="progress-label">{{ run.progress }}%</span>
          </span>

          <!-- Started at -->
          <span class="col col--date">
            {{ run.started_at ? new Date(run.started_at).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' }) : '—' }}
          </span>
        </button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.runs-dashboard {
  display: flex;
  flex-direction: column;
  gap: var(--s-5, 1.25rem);
}

/* Header */
.dashboard-header {
  display: flex;
  flex-direction: column;
  gap: var(--s-4, 1rem);
}

.header-title-row {
  display: flex;
  align-items: center;
  gap: var(--s-4, 1rem);
  flex-wrap: wrap;
}

.dashboard-title {
  font-family: var(--ff-sans);
  font-weight: 600;
  font-size: 1.5rem;
  letter-spacing: -0.01em;
  margin: 0;
  flex: 1;
}

.live-indicator {
  font-family: var(--ff-mono, monospace);
  font-size: 11px;
  letter-spacing: var(--ls-mono, 0.06em);
  text-transform: uppercase;
  color: var(--fg-muted, #888);
  border: 1px solid var(--rule, #ddd);
  padding: 2px 8px;
}

.live-indicator--active {
  color: var(--accent, #2563eb);
  border-color: var(--accent, #2563eb);
}

.refresh-btn {
  background: transparent;
  border: 1px solid var(--rule-strong, #ccc);
  color: var(--fg, #111);
  cursor: pointer;
  padding: 4px 10px;
  font-size: 1rem;
  line-height: 1;
}
.refresh-btn:hover { background: var(--bg-elevated, #f5f5f5); }
.refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* Filter pills */
.filter-pills {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2, 0.5rem);
}

.pill {
  font-family: var(--ff-mono, monospace);
  font-size: 11px;
  letter-spacing: var(--ls-mono, 0.06em);
  text-transform: uppercase;
  background: transparent;
  border: 1px solid var(--rule-strong, #ccc);
  color: var(--fg, #111);
  padding: 5px 12px;
  cursor: pointer;
  transition: background 0.1s;
}

.pill:hover { background: var(--bg-elevated, #f5f5f5); }
.pill:focus-visible { outline: 2px solid var(--accent, #2563eb); outline-offset: 2px; }
.pill--active {
  background: var(--accent, #2563eb);
  border-color: var(--accent, #2563eb);
  color: #fff;
}

/* Search */
.search-row { display: flex; }
.search-input {
  flex: 1;
  background: var(--bg-elevated, #f5f5f5);
  border: 1px solid var(--rule-strong, #ccc);
  color: var(--fg, #111);
  padding: 6px 12px;
  font-size: 13px;
  font-family: var(--ff-mono, monospace);
  max-width: 400px;
}
.search-input:focus { outline: 2px solid var(--accent, #2563eb); outline-offset: 1px; }

/* Error / State messages */
.error-banner {
  padding: var(--s-4, 1rem);
  background: #fee2e2;
  border: 1px solid #f87171;
  color: #7f1d1d;
  font-size: 13px;
}

.state-message {
  padding: var(--s-5, 1.25rem);
  color: var(--fg-muted, #888);
  font-family: var(--ff-mono, monospace);
  font-size: 12px;
  text-align: center;
  border-top: 1px solid var(--rule, #ddd);
}

/* Runs list */
.runs-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid var(--rule, #ddd);
}

.run-row {
  border-bottom: 1px solid var(--rule, #ddd);
}

.run-row-btn {
  display: grid;
  grid-template-columns: 2rem 1fr 2fr 7rem 7rem;
  align-items: center;
  gap: var(--s-3, 0.75rem);
  width: 100%;
  padding: var(--s-3, 0.75rem) var(--s-4, 1rem);
  background: transparent;
  border: 0;
  cursor: pointer;
  text-align: left;
  color: var(--fg, #111);
  transition: background 0.1s;
}

.run-row-btn:hover { background: var(--bg-elevated, #f5f5f5); }
.run-row-btn:focus-visible { outline: 2px solid var(--accent, #2563eb); outline-offset: -2px; }

/* Badges */
.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  font-size: 12px;
  border-radius: 2px;
  font-weight: 600;
}

.badge--active { background: #dbeafe; color: #1d4ed8; }
.badge--done   { background: #dcfce7; color: #166534; }
.badge--failed { background: #fee2e2; color: #991b1b; }

/* Columns */
.col {
  font-size: 12px;
  font-family: var(--ff-mono, monospace);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.col--type    { color: var(--fg-muted, #888); }
.col--entity  { font-weight: 500; }
.col--date    { color: var(--fg-muted, #888); }

/* Progress */
.col--progress {
  display: flex;
  align-items: center;
  gap: 6px;
}

.progress-bar {
  flex: 1;
  height: 4px;
  background: var(--rule, #ddd);
  border-radius: 2px;
  overflow: hidden;
  display: block;
}

.progress-fill {
  height: 100%;
  background: var(--accent, #2563eb);
  border-radius: 2px;
  transition: width 0.3s;
  display: block;
}

.progress-label {
  min-width: 2.5rem;
  text-align: right;
}
</style>
