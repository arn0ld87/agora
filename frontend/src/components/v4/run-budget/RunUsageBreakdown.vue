<script setup lang="ts">
/**
 * RunUsageBreakdown — Abschlussanalyse des Ressourcenverbrauchs eines Runs
 * (Issue #764).
 *
 * Gesamtwerte mit Status-Badges, optionale Gegenüberstellung Schätzung vs.
 * Ist, Tabellen pro Stage/Provider/Modell (sortiert nach total_tokens desc,
 * größter Verbraucher markiert) sowie Budget-Warnungen und Abbruchgrund.
 * Unbekannte Werte rendern als "—" mit Status-Badge — niemals als 0.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Card from '../forms/Card.vue'
import Badge from '../forms/Badge.vue'
import Alert from '../data/Alert.vue'
import type {
  BudgetDimension,
  CostStatus,
  MeasurementStatus,
  PreflightEstimate,
  RunBudgetStatus,
  RunUsage,
  TerminationReason,
  TokensStatus,
  UsageMetrics,
} from '../../../contracts/runBudgetContract'
import {
  formatCostMicros,
  formatDuration,
  formatDurationMs,
  formatRange,
  formatTokens,
} from '../../../utils/format'

const props = withDefaults(
  defineProps<{
    usage: RunUsage
    budget?: RunBudgetStatus | null
    estimate?: PreflightEstimate | null
  }>(),
  {
    budget: null,
    estimate: null,
  },
)

const { t } = useI18n()

const COST_STATUS_LABEL: Record<CostStatus, string> = {
  measured: 'runBudget.costStatusMeasured',
  estimated: 'runBudget.costStatusEstimated',
  free: 'runBudget.costStatusFree',
  unknown: 'runBudget.costStatusUnknown',
}

const COST_STATUS_TONE: Record<CostStatus, 'green' | 'blue' | 'teal' | 'gray'> = {
  measured: 'green',
  estimated: 'blue',
  free: 'teal',
  unknown: 'gray',
}

const TOKENS_STATUS_LABEL: Record<TokensStatus, string> = {
  measured: 'runBudget.costStatusMeasured',
  partial: 'runBudget.tokensStatusPartial',
  unknown: 'runBudget.costStatusUnknown',
}

const TOKENS_STATUS_TONE: Record<TokensStatus, 'green' | 'orange' | 'gray'> = {
  measured: 'green',
  partial: 'orange',
  unknown: 'gray',
}

const MEASUREMENT_LABEL: Record<MeasurementStatus, string> = {
  complete: 'runBudget.measurementComplete',
  partial: 'runBudget.measurementPartial',
  unknown: 'runBudget.measurementUnknown',
}

const MEASUREMENT_TONE: Record<MeasurementStatus, 'green' | 'orange' | 'gray'> = {
  complete: 'green',
  partial: 'orange',
  unknown: 'gray',
}

/** Budget-Dimension → passender Termination-Reason-Key für die Anzeige. */
const DIMENSION_TO_TERMINATION: Record<BudgetDimension, TerminationReason> = {
  tokens: 'budget_tokens',
  cost: 'budget_cost',
  time: 'budget_time',
  calls: 'budget_calls',
}

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

const totals = computed(() => props.usage.totals)

const showMeasurementFlag = computed(
  () => props.usage.measurement_status !== 'complete',
)

/** Zählerformat für LLM-Aufrufe (kein k/M-Suffix). */
function formatCount(value: number | null | undefined, locale = 'de-DE'): string {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(value)
}

// --- Schätzung vs. Ist ---
interface EstimateVsActualRow {
  key: 'tokens' | 'cost' | 'duration'
  labelKey: string
  estimated: string
  actual: string
}

const estimateVsActual = computed<EstimateVsActualRow[]>(() => {
  if (!props.estimate) return []
  const estimate = props.estimate
  return [
    {
      key: 'tokens',
      labelKey: 'runBudget.estimateTokens',
      estimated: formatRange(
        estimate.estimated_tokens_low,
        estimate.estimated_tokens_high,
        formatTokens,
      ),
      actual: formatTokens(totals.value.total_tokens),
    },
    {
      key: 'cost',
      labelKey: 'runBudget.estimateCost',
      estimated: formatRange(
        estimate.estimated_cost_micros_low,
        estimate.estimated_cost_micros_high,
        formatCostMicros,
      ),
      actual: formatCostMicros(totals.value.cost_micros),
    },
    {
      key: 'duration',
      labelKey: 'runBudget.estimateDuration',
      estimated: formatRange(
        estimate.estimated_duration_seconds_low,
        estimate.estimated_duration_seconds_high,
        formatDuration,
      ),
      actual: formatDurationMs(totals.value.duration_ms),
    },
  ]
})

// --- Tabellen pro Dimension ---
interface BreakdownRow {
  name: string
  metrics: UsageMetrics
  isTop: boolean
}

function toSortedRows(record: Record<string, UsageMetrics>): BreakdownRow[] {
  const entries = Object.entries(record).sort(
    (a, b) => (b[1].total_tokens ?? -1) - (a[1].total_tokens ?? -1),
  )
  // Größter Verbraucher = erste Zeile mit bekanntem Verbrauch > 0.
  const topIndex = entries.findIndex(([, m]) => (m.total_tokens ?? 0) > 0)
  return entries.map(([name, metrics], index) => ({
    name,
    metrics,
    isTop: index === topIndex,
  }))
}

const stageRows = computed(() => toSortedRows(props.usage.by_stage))
const providerRows = computed(() => toSortedRows(props.usage.by_provider))
const modelRows = computed(() => toSortedRows(props.usage.by_model))

const warnings = computed(() => props.budget?.warnings ?? [])

const exceededReasonKey = computed(() => {
  if (props.budget?.status !== 'exceeded') return null
  const dimension = props.budget.exceeded_dimension
  if (!dimension) return null
  return TERMINATION_LABEL[DIMENSION_TO_TERMINATION[dimension]]
})

const pricingMeta = computed(() => {
  const version = props.usage.pricing_version
  const source = props.usage.pricing_source
  if (!version && !source) return null
  return t('runBudget.pricingMeta', {
    version: version ?? '—',
    source: source ?? '—',
  })
})
</script>

<template>
  <Card :title="t('runBudget.breakdownTitle')" class="rb-breakdown">
    <template #right>
      <Badge
        v-if="showMeasurementFlag"
        :tone="MEASUREMENT_TONE[usage.measurement_status]"
        data-testid="measurement-badge"
      >
        {{ t(MEASUREMENT_LABEL[usage.measurement_status]) }}
      </Badge>
    </template>

    <!-- Gesamtwerte -->
    <dl class="rb-breakdown__totals" data-testid="usage-totals">
      <div class="rb-breakdown__total">
        <dt>{{ t('runBudget.totalTokens') }}</dt>
        <dd data-testid="usage-total-tokens">
          {{ formatTokens(totals.total_tokens) }}
          <Badge :tone="TOKENS_STATUS_TONE[totals.tokens_status]" :dot="false">
            {{ t(TOKENS_STATUS_LABEL[totals.tokens_status]) }}
          </Badge>
        </dd>
      </div>
      <div class="rb-breakdown__total">
        <dt>{{ t('runBudget.inputTokens') }}</dt>
        <dd data-testid="usage-input-tokens">{{ formatTokens(totals.input_tokens) }}</dd>
      </div>
      <div class="rb-breakdown__total">
        <dt>{{ t('runBudget.outputTokens') }}</dt>
        <dd data-testid="usage-output-tokens">{{ formatTokens(totals.output_tokens) }}</dd>
      </div>
      <div class="rb-breakdown__total">
        <dt>{{ t('runBudget.cost') }}</dt>
        <dd data-testid="usage-cost">
          {{ formatCostMicros(totals.cost_micros) }}
          <Badge :tone="COST_STATUS_TONE[totals.cost_status]" :dot="false">
            {{ t(COST_STATUS_LABEL[totals.cost_status]) }}
          </Badge>
        </dd>
      </div>
      <div class="rb-breakdown__total">
        <dt>{{ t('runBudget.duration') }}</dt>
        <dd data-testid="usage-duration">{{ formatDurationMs(totals.duration_ms) }}</dd>
      </div>
      <div class="rb-breakdown__total">
        <dt>{{ t('runBudget.llmCalls') }}</dt>
        <dd data-testid="usage-calls">{{ formatCount(totals.llm_calls) }}</dd>
      </div>
    </dl>

    <!-- Schätzung vs. Ist -->
    <template v-if="estimateVsActual.length > 0">
      <p class="rb-breakdown__section-label">{{ t('runBudget.estimateVsActualTitle') }}</p>
      <table class="rb-breakdown__table" data-testid="estimate-vs-actual">
        <thead>
          <tr>
            <th scope="col">{{ t('runBudget.colName') }}</th>
            <th scope="col">{{ t('runBudget.estimatedColumn') }}</th>
            <th scope="col">{{ t('runBudget.actualColumn') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in estimateVsActual" :key="row.key">
            <th scope="row">{{ t(row.labelKey) }}</th>
            <td>{{ row.estimated }}</td>
            <td>{{ row.actual }}</td>
          </tr>
        </tbody>
      </table>
    </template>

    <!-- Pro Stage -->
    <template v-if="stageRows.length > 0">
      <p class="rb-breakdown__section-label">{{ t('runBudget.byStageTitle') }}</p>
      <table class="rb-breakdown__table" data-testid="usage-by-stage">
        <thead>
          <tr>
            <th scope="col">{{ t('runBudget.colStage') }}</th>
            <th scope="col">{{ t('runBudget.totalTokens') }}</th>
            <th scope="col">{{ t('runBudget.cost') }}</th>
            <th scope="col">{{ t('runBudget.llmCalls') }}</th>
            <th scope="col">{{ t('runBudget.duration') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in stageRows" :key="row.name" :class="{ 'rb-breakdown__row--top': row.isTop }">
            <th scope="row">
              {{ row.name }}
              <Badge v-if="row.isTop" tone="purple" :dot="false" class="rb-breakdown__top-badge">
                {{ t('runBudget.topConsumer') }}
              </Badge>
            </th>
            <td>{{ formatTokens(row.metrics.total_tokens) }}</td>
            <td>{{ formatCostMicros(row.metrics.cost_micros) }}</td>
            <td>{{ formatCount(row.metrics.llm_calls) }}</td>
            <td>{{ formatDurationMs(row.metrics.duration_ms) }}</td>
          </tr>
        </tbody>
      </table>
    </template>

    <!-- Pro Provider -->
    <template v-if="providerRows.length > 0">
      <p class="rb-breakdown__section-label">{{ t('runBudget.byProviderTitle') }}</p>
      <table class="rb-breakdown__table" data-testid="usage-by-provider">
        <thead>
          <tr>
            <th scope="col">{{ t('runBudget.colProvider') }}</th>
            <th scope="col">{{ t('runBudget.totalTokens') }}</th>
            <th scope="col">{{ t('runBudget.cost') }}</th>
            <th scope="col">{{ t('runBudget.llmCalls') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in providerRows" :key="row.name">
            <th scope="row">{{ row.name }}</th>
            <td>{{ formatTokens(row.metrics.total_tokens) }}</td>
            <td>{{ formatCostMicros(row.metrics.cost_micros) }}</td>
            <td>{{ formatCount(row.metrics.llm_calls) }}</td>
          </tr>
        </tbody>
      </table>
    </template>

    <!-- Pro Modell -->
    <template v-if="modelRows.length > 0">
      <p class="rb-breakdown__section-label">{{ t('runBudget.byModelTitle') }}</p>
      <table class="rb-breakdown__table" data-testid="usage-by-model">
        <thead>
          <tr>
            <th scope="col">{{ t('runBudget.colModel') }}</th>
            <th scope="col">{{ t('runBudget.totalTokens') }}</th>
            <th scope="col">{{ t('runBudget.cost') }}</th>
            <th scope="col">{{ t('runBudget.llmCalls') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in modelRows" :key="row.name">
            <th scope="row">{{ row.name }}</th>
            <td>{{ formatTokens(row.metrics.total_tokens) }}</td>
            <td>{{ formatCostMicros(row.metrics.cost_micros) }}</td>
            <td>{{ formatCount(row.metrics.llm_calls) }}</td>
          </tr>
        </tbody>
      </table>
    </template>

    <!-- Budget-Warnungen + Abbruchgrund -->
    <Alert
      v-if="exceededReasonKey"
      tone="danger"
      :title="t('runBudget.budgetStopTitle')"
      data-testid="budget-exceeded-banner"
    >
      {{ t(exceededReasonKey) }}
    </Alert>

    <div v-if="warnings.length > 0" class="rb-breakdown__warnings">
      <Alert
        v-for="(warning, index) in warnings"
        :key="`${warning.dimension}-${warning.threshold}-${index}`"
        :tone="warning.severity === 'hard' ? 'danger' : 'warning'"
        data-testid="budget-warning"
      >
        {{ warning.message }}
      </Alert>
    </div>

    <p v-if="pricingMeta" class="rb-breakdown__meta">{{ pricingMeta }}</p>
  </Card>
</template>

<style scoped>
.rb-breakdown__totals {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  margin: 0 0 14px;
}

.rb-breakdown__total dt {
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

.rb-breakdown__total dd {
  margin: 4px 0 0;
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: 14px;
  color: var(--text-primary);
}

.rb-breakdown__section-label {
  margin: 14px 0 6px;
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

.rb-breakdown__table {
  width: 100%;
  border-collapse: collapse;
  font-family: var(--font-sans);
  font-size: 13px;
}

.rb-breakdown__table th,
.rb-breakdown__table td {
  padding: 6px 8px;
  text-align: left;
  border-bottom: 1px solid var(--hairline);
}

.rb-breakdown__table thead th {
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

.rb-breakdown__table tbody th {
  font-weight: 500;
  color: var(--text-primary);
}

.rb-breakdown__table td {
  font-family: var(--font-mono);
  font-size: 12.5px;
  color: var(--text-secondary);
}

.rb-breakdown__row--top th {
  color: var(--accent);
}

.rb-breakdown__top-badge {
  margin-left: 8px;
}

.rb-breakdown__warnings {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 12px;
}

.rb-breakdown__meta {
  margin: 12px 0 0;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-tertiary);
}
</style>
