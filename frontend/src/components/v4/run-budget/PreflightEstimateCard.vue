<script setup lang="ts">
/**
 * PreflightEstimateCard — ehrlich gekennzeichnete Kosten-/Token-/Zeitschätzung
 * vor dem Run-Start (Issue #764).
 *
 * Zeigt ausschließlich Backend-Schätzwerte (is_estimate=true), niemals
 * selbst berechnete Preise. Unbekannte Werte rendern als "—" plus
 * Status-Badge — niemals als 0.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Card from '../forms/Card.vue'
import Badge from '../forms/Badge.vue'
import Alert from '../data/Alert.vue'
import type {
  CostStatus,
  DataQuality,
  PreflightEstimate,
} from '../../../contracts/runBudgetContract'
import {
  formatCostMicros,
  formatDuration,
  formatRange,
  formatTokens,
} from '../../../utils/format'

const props = withDefaults(
  defineProps<{
    estimate: PreflightEstimate | null
    loading?: boolean
    error?: string | null
  }>(),
  {
    loading: false,
    error: null,
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

const QUALITY_LABEL: Record<DataQuality, string> = {
  high: 'runBudget.qualityHigh',
  medium: 'runBudget.qualityMedium',
  low: 'runBudget.qualityLow',
  unknown: 'runBudget.qualityUnknown',
}

const QUALITY_TONE: Record<DataQuality, 'green' | 'blue' | 'orange' | 'gray'> = {
  high: 'green',
  medium: 'blue',
  low: 'orange',
  unknown: 'gray',
}

function costStatusLabel(status: CostStatus): string {
  return t(COST_STATUS_LABEL[status])
}

function costStatusTone(status: CostStatus): 'green' | 'blue' | 'teal' | 'gray' {
  return COST_STATUS_TONE[status]
}

const tokensRange = computed(() =>
  props.estimate
    ? formatRange(
        props.estimate.estimated_tokens_low,
        props.estimate.estimated_tokens_high,
        formatTokens,
      )
    : '—',
)

const costRange = computed(() =>
  props.estimate
    ? formatRange(
        props.estimate.estimated_cost_micros_low,
        props.estimate.estimated_cost_micros_high,
        formatCostMicros,
      )
    : '—',
)

const durationRange = computed(() =>
  props.estimate
    ? formatRange(
        props.estimate.estimated_duration_seconds_low,
        props.estimate.estimated_duration_seconds_high,
        formatDuration,
      )
    : '—',
)
</script>

<template>
  <Card :title="t('runBudget.estimateTitle')" class="rb-preflight">
    <template #right>
      <Badge v-if="estimate" tone="blue" data-testid="estimate-badge">
        {{ t('runBudget.estimateBadge') }}
      </Badge>
    </template>

    <p v-if="loading" class="rb-preflight__loading" aria-live="polite">
      {{ t('runBudget.estimateLoading') }}
    </p>

    <Alert v-else-if="error" tone="danger" data-testid="estimate-error">
      {{ error }}
    </Alert>

    <div v-else-if="!estimate" class="rb-preflight__empty">
      <p class="rb-preflight__empty-text">{{ t('runBudget.estimateEmpty') }}</p>
    </div>

    <div v-else class="rb-preflight__body">
      <dl class="rb-preflight__ranges">
        <div class="rb-preflight__range">
          <dt>{{ t('runBudget.estimateTokens') }}</dt>
          <dd data-testid="estimate-tokens">{{ tokensRange }}</dd>
        </div>
        <div class="rb-preflight__range">
          <dt>{{ t('runBudget.estimateCost') }}</dt>
          <dd data-testid="estimate-cost">
            {{ costRange }}
            <Badge :tone="costStatusTone(estimate.cost_status)" :dot="false">
              {{ costStatusLabel(estimate.cost_status) }}
            </Badge>
          </dd>
        </div>
        <div class="rb-preflight__range">
          <dt>{{ t('runBudget.estimateDuration') }}</dt>
          <dd data-testid="estimate-duration">{{ durationRange }}</dd>
        </div>
        <div class="rb-preflight__range">
          <dt>{{ t('runBudget.estimateDataQuality') }}</dt>
          <dd>
            <Badge :tone="QUALITY_TONE[estimate.data_quality]" :dot="false" data-testid="estimate-quality">
              {{ t(QUALITY_LABEL[estimate.data_quality]) }}
            </Badge>
          </dd>
        </div>
      </dl>

      <div v-if="estimate.models.length > 0" class="rb-preflight__models">
        <p class="rb-preflight__section-label">{{ t('runBudget.estimateModels') }}</p>
        <ul class="rb-preflight__model-list">
          <li
            v-for="model in estimate.models"
            :key="`${model.stage}-${model.provider_id}-${model.model_id}`"
            class="rb-preflight__model"
          >
            <span class="rb-preflight__model-stage">{{ model.stage }}</span>
            <span class="rb-preflight__model-name">
              {{ model.provider_id }}/{{ model.model_id }}
            </span>
            <Badge :tone="costStatusTone(model.cost_status)" :dot="false">
              {{ costStatusLabel(model.cost_status) }}
            </Badge>
          </li>
        </ul>
      </div>

      <Alert
        v-if="estimate.warnings.length > 0"
        tone="warning"
        :title="t('runBudget.estimateWarnings')"
        data-testid="estimate-warnings"
      >
        <ul class="rb-preflight__warnings">
          <li v-for="(warning, index) in estimate.warnings" :key="index">
            {{ warning }}
          </li>
        </ul>
      </Alert>

      <p class="rb-preflight__meta">
        {{ t('runBudget.pricingMeta', { version: estimate.pricing_version, source: estimate.pricing_source }) }}
      </p>
    </div>
  </Card>
</template>

<style scoped>
.rb-preflight__loading {
  margin: 0;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-tertiary);
}

.rb-preflight__empty {
  padding: 12px;
  border: 1px dashed var(--hairline);
  border-radius: var(--r-4, 8px);
  background: var(--surface-inset);
}

.rb-preflight__empty-text {
  margin: 0;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.45;
}

.rb-preflight__body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rb-preflight__ranges {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  margin: 0;
}

.rb-preflight__range dt {
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

.rb-preflight__range dd {
  margin: 4px 0 0;
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: 14px;
  color: var(--text-primary);
}

.rb-preflight__section-label {
  margin: 0 0 6px;
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

.rb-preflight__model-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rb-preflight__model {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border-radius: var(--r-4, 8px);
  background: var(--surface-inset);
  font-family: var(--font-sans);
  font-size: 13px;
}

.rb-preflight__model-stage {
  color: var(--text-secondary);
  min-width: 0;
}

.rb-preflight__model-name {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-primary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rb-preflight__warnings {
  margin: 4px 0 0;
  padding-left: 16px;
}

.rb-preflight__meta {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-tertiary);
}
</style>
