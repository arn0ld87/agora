<script setup lang="ts">
/**
 * RunResourceMonitor — Live-Verbrauch vs. Budget während eines Runs
 * (Issue #764).
 *
 * Pollt GET /api/runs/<runId> alle 5 s, solange der Run-Status
 * "pending"/"processing" ist, und liest budget/usage/termination_reason aus
 * der angereicherten Run-Detail-Antwort. Beim Übergang in einen terminalen
 * Status wird ein letzter Tick gefahren, damit die Endwerte stehen bleiben.
 *
 * Fortschrittsbalken nur für gesetzte Budget-Dimensionen; unbekannte
 * Verbrauchswerte rendern als "—" (niemals 0).
 */
import { computed, ref, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import Card from '../forms/Card.vue'
import Badge from '../forms/Badge.vue'
import Alert from '../data/Alert.vue'
import { usePolling } from '../../../composables/usePolling'
import { getRun } from '../../../api/runs'
import type { RunRecord } from '../../../types/run'
import type {
  BudgetDimension,
  BudgetState,
  RunBudgetStatus,
  RunUsage,
  TerminationReason,
} from '../../../contracts/runBudgetContract'
import {
  formatCostMicros,
  formatDuration,
  formatTokens,
} from '../../../utils/format'

const props = withDefaults(
  defineProps<{
    runId: string
    /** Kanonischer Run-Status (pending | processing | …). */
    status: string
    terminationReason?: TerminationReason | null
  }>(),
  {
    terminationReason: null,
  },
)

const { t, locale } = useI18n()

const POLL_INTERVAL_MS = 5000
/** Status-Werte, bei denen der Verbrauch weiter wachsen kann. */
const ACTIVE_STATUSES = new Set(['pending', 'processing'])

const budget = ref<RunBudgetStatus | null>(null)
const usage = ref<RunUsage | null>(null)
const polledTermination = ref<TerminationReason | null>(null)
const loadError = ref(false)

// Issue #764 (Codex P1): Wall-Clock für die Zeit-Budget-Dimension.
// consumed.duration_ms ist die aufsummierte LLM-Call-Latenz und nicht
// der Zeitverbrauch eines gesamten Runs. Wall-Clock wird aus
// RunDetail.started_at und einem 1s-Ticker abgeleitet, solange der Run
// aktiv ist; bei Terminal-Status friert der Wert ein.
const startedAt = ref<number | null>(null)
const wallClockNow = ref<number>(Date.now())

const WALL_CLOCK_TICK_MS = 1000
let wallClockInterval: ReturnType<typeof setInterval> | null = null

function startWallClockTicker(): void {
  if (wallClockInterval !== null) return
  wallClockInterval = setInterval(() => {
    wallClockNow.value = Date.now()
  }, WALL_CLOCK_TICK_MS)
}
function stopWallClockTicker(): void {
  if (wallClockInterval === null) return
  clearInterval(wallClockInterval)
  wallClockInterval = null
}

function parseStartedAtMs(value: unknown): number | null {
  if (typeof value !== 'string' || value.length === 0) return null
  const ms = Date.parse(value)
  return Number.isFinite(ms) ? ms : null
}

async function tick(): Promise<void> {
  const res = await getRun(props.runId)
  if (!res?.success) return
  const data = res.data as RunRecord | undefined
  budget.value = data?.budget ?? null
  usage.value = data?.usage ?? null
  polledTermination.value = data?.termination_reason ?? null
  // started_at einmalig oder bei Wechsel neu setzen; bei Terminal-Status
  // bleibt der zuletzt gesehene Wert stehen (Wall-Clock friert ein).
  const next = parseStartedAtMs(data?.started_at)
  if (next !== null) startedAt.value = next
  loadError.value = false
}

const polling = usePolling(tick, POLL_INTERVAL_MS, {
  onError: () => {
    loadError.value = true
  },
})

const isActive = computed(() => ACTIVE_STATUSES.has(props.status))

watch(
  isActive,
  (active, wasActive) => {
    if (active) {
      void polling.start({ immediate: true })
      startWallClockTicker()
    } else {
      polling.stop()
      stopWallClockTicker()
      // Letzter Tick nach Run-Ende: Endverbrauch + Abbruchgrund stehen lassen.
      if (wasActive) void polling.tick()
    }
  },
  { immediate: true },
)

watch(
  () => props.runId,
  (next, prev) => {
    if (next === prev) return
    budget.value = null
    usage.value = null
    polledTermination.value = null
    startedAt.value = null
    if (isActive.value) {
      polling.stop()
      void polling.start({ immediate: true })
      startWallClockTicker()
    } else {
      stopWallClockTicker()
    }
  },
)

const effectiveTermination = computed(
  () => props.terminationReason ?? polledTermination.value,
)

const isBudgetStop = computed(() =>
  (effectiveTermination.value ?? '').startsWith('budget_'),
)

const TERMINATION_LABEL: Record<TerminationReason, string> = {
  completed: 'runBudget.terminationCompleted',
  error: 'runBudget.terminationError',
  user_cancel: 'runBudget.terminationUserCancel',
  user_stop: 'runBudget.terminationUserStop',
  budget_tokens: 'runBudget.terminationBudgetTokens',
  budget_cost: 'runBudget.terminationBudgetCost',
  budget_time: 'runBudget.terminationBudgetTime',
  budget_calls: 'runBudget.terminationBudgetCalls',
}

const BUDGET_STATE_LABEL: Record<BudgetState, string> = {
  ok: 'runBudget.statusOk',
  warning: 'runBudget.statusWarning',
  exceeded: 'runBudget.statusExceeded',
}

const BUDGET_STATE_TONE: Record<BudgetState, 'green' | 'orange' | 'red'> = {
  ok: 'green',
  warning: 'orange',
  exceeded: 'red',
}

const DIMENSION_LABEL: Record<BudgetDimension, string> = {
  tokens: 'runBudget.dimensionTokens',
  cost: 'runBudget.dimensionCost',
  time: 'runBudget.dimensionTime',
  calls: 'runBudget.dimensionCalls',
}

/** Zählerformat für LLM-Aufrufe (kein k/M-Suffix wie bei Tokens).
 * Locale kommt aus useI18n(); Fallback 'de-DE' nur fuer Nicht-Vue-Aufrufer.
 */
function formatCount(value: number | null | undefined, overrideLocale?: string): string {
  if (value === null || value === undefined) return '—'
  const activeLocale = overrideLocale ?? locale.value
  return new Intl.NumberFormat(activeLocale, { maximumFractionDigits: 0 }).format(value)
}

interface DimensionRow {
  key: BudgetDimension
  consumed: number | null
  limit: number
  /** 0–100; null wenn Verbrauch unbekannt. */
  percent: number | null
  consumedText: string
  limitText: string
  remainingText: string
}

function buildRow(
  key: BudgetDimension,
  limit: number,
  consumed: number | null,
  format: (value: number | null | undefined) => string,
): DimensionRow {
  const percent =
    consumed === null ? null : Math.min(100, (consumed / limit) * 100)
  const remaining =
    consumed === null ? null : Math.max(0, limit - consumed)
  return {
    key,
    consumed,
    limit,
    percent,
    consumedText: format(consumed),
    limitText: format(limit),
    remainingText: format(remaining),
  }
}

const dimensionRows = computed<DimensionRow[]>(() => {
  const config = budget.value?.config
  if (!config) return []
  const consumed = budget.value?.consumed
  const rows: DimensionRow[] = []
  if (config.max_tokens) {
    rows.push(
      buildRow('tokens', config.max_tokens, consumed?.total_tokens ?? null, formatTokens),
    )
  }
  if (config.max_cost_micros) {
    rows.push(
      buildRow('cost', config.max_cost_micros, consumed?.cost_micros ?? null, formatCostMicros),
    )
  }
  if (config.max_duration_seconds) {
    // Issue #764 (Codex P1): Wall-Clock aus started_at + 1s-Ticker.
    // consumed.duration_ms ist die Summe der LLM-Call-Latenzen und
    // unterschätzt den Laufzeitverbrauch eines Runs, in dem das
    // Modell zwischen Calls wartet (Plan-Phase, Tool-Roundtrips,
    // I/O). Wall-Clock ist die einzige ehrliche Messgröße für das
    // max_duration_seconds-Budget.
    const consumedSeconds =
      startedAt.value === null
        ? null
        : Math.max(0, (wallClockNow.value - startedAt.value) / 1000)
    rows.push(
      buildRow('time', config.max_duration_seconds, consumedSeconds, formatDuration),
    )
  }
  if (config.max_llm_calls) {
    rows.push(
      buildRow('calls', config.max_llm_calls, consumed?.llm_calls ?? null, formatCount),
    )
  }
  return rows
})

const warnings = computed(() => budget.value?.warnings ?? [])

onUnmounted(() => {
  stopWallClockTicker()
})
</script>

<template>
  <Card :title="t('runBudget.monitorTitle')" class="rb-monitor">
    <template #right>
      <Badge
        v-if="budget"
        :tone="BUDGET_STATE_TONE[budget.status]"
        data-testid="budget-state-badge"
      >
        {{ t(BUDGET_STATE_LABEL[budget.status]) }}
      </Badge>
    </template>

    <Alert
      v-if="isBudgetStop && effectiveTermination"
      tone="danger"
      :title="t('runBudget.budgetStopTitle')"
      data-testid="budget-stop-banner"
    >
      {{ t(TERMINATION_LABEL[effectiveTermination]) }}
    </Alert>

    <template v-if="dimensionRows.length > 0">
      <div
        v-for="row in dimensionRows"
        :key="row.key"
        class="rb-monitor__row"
        :data-testid="`budget-row-${row.key}`"
      >
        <div class="rb-monitor__row-head">
          <span class="rb-monitor__row-label">{{ t(DIMENSION_LABEL[row.key]) }}</span>
          <span class="rb-monitor__row-values">
            <span class="rb-monitor__consumed">{{ row.consumedText }}</span>
            {{ t('runBudget.ofLimit') }} {{ row.limitText }}
            <span class="rb-monitor__remaining">
              · {{ row.remainingText }} {{ t('runBudget.remainingLabel') }}
            </span>
          </span>
        </div>
        <div
          class="rb-monitor__bar"
          :class="{ 'rb-monitor__bar--unknown': row.percent === null }"
          role="progressbar"
          :aria-label="t(DIMENSION_LABEL[row.key])"
          aria-valuemin="0"
          :aria-valuemax="row.limit"
          :aria-valuenow="row.consumed ?? undefined"
        >
          <div
            class="rb-monitor__bar-fill"
            :class="{ 'rb-monitor__bar-fill--exceeded': row.percent !== null && row.percent >= 100 }"
            :style="{ width: `${row.percent ?? 0}%` }"
          />
        </div>
      </div>
    </template>

    <p v-else class="rb-monitor__no-budget" data-testid="budget-none">
      {{ t('runBudget.monitorNoBudget') }}
    </p>

    <template v-if="warnings.length > 0">
      <p class="rb-monitor__warnings-label">{{ t('runBudget.warningsTitle') }}</p>
      <div class="rb-monitor__warnings">
        <Alert
          v-for="(warning, index) in warnings"
          :key="`${warning.dimension}-${warning.threshold}-${index}`"
          :tone="warning.severity === 'hard' ? 'danger' : 'warning'"
          :title="t(DIMENSION_LABEL[warning.dimension])"
          data-testid="budget-warning"
        >
          {{ warning.message }}
        </Alert>
      </div>
    </template>

    <p v-if="loadError" class="rb-monitor__error" role="alert">
      {{ t('errors.network') }}
    </p>
  </Card>
</template>

<style scoped>
.rb-monitor__row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 10px;
}

.rb-monitor__row-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  font-family: var(--font-sans);
  font-size: 12.5px;
}

.rb-monitor__row-label {
  font-weight: 500;
  color: var(--text-secondary);
}

.rb-monitor__row-values {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--text-tertiary);
}

.rb-monitor__consumed {
  color: var(--text-primary);
  font-weight: 600;
}

.rb-monitor__remaining {
  color: var(--text-tertiary);
}

.rb-monitor__bar {
  height: 6px;
  border-radius: var(--r-pill, 999px);
  background: var(--surface-inset, #f2f2f7);
  overflow: hidden;
}

.rb-monitor__bar-fill {
  height: 100%;
  border-radius: inherit;
  background: var(--accent);
  transition: width 300ms ease;
}

.rb-monitor__bar-fill--exceeded {
  background: var(--status-red);
}

.rb-monitor__bar--unknown .rb-monitor__bar-fill {
  background: var(--hairline);
}

.rb-monitor__no-budget {
  margin: 4px 0 0;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-tertiary);
}

.rb-monitor__warnings-label {
  margin: 14px 0 6px;
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

.rb-monitor__warnings {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.rb-monitor__error {
  margin: 10px 0 0;
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--status-red);
}

@media (prefers-reduced-motion: reduce) {
  .rb-monitor__bar-fill {
    transition: none;
  }
}
</style>
