<template>
  <details v-if="entries && entries.length > 0" class="report-provenance" :open="defaultOpen">
    <summary class="report-provenance__summary">
      {{ t('report.provenance.title') }}
      <span class="report-provenance__count">({{ entries.length }})</span>
    </summary>
    <table class="report-provenance__table">
      <thead>
        <tr>
          <th>{{ t('report.provenance.stage') }}</th>
          <th>{{ t('report.provenance.provider') }}</th>
          <th>{{ t('report.provenance.model') }}</th>
          <th class="num">{{ t('report.provenance.promptTokens') }}</th>
          <th class="num">{{ t('report.provenance.completionTokens') }}</th>
          <th class="num">{{ t('report.provenance.latencyMs') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(entry, idx) in entries" :key="`prov-${idx}`">
          <td>{{ entry.stage }}</td>
          <td>{{ entry.provider }}</td>
          <td class="model-id">{{ entry.model_id }}</td>
          <td class="num">{{ entry.prompt_tokens ?? '—' }}</td>
          <td class="num">{{ entry.completion_tokens ?? '—' }}</td>
          <td class="num">{{ formatLatency(entry.latency_ms) }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!hasAnyMetrics" class="report-provenance__hint">
      {{ t('report.provenance.noMetricsHint') }}
    </p>
  </details>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

export interface ModelAttributionEntry {
  stage: string
  provider: string
  model_id: string
  prompt_tokens?: number | null
  completion_tokens?: number | null
  latency_ms?: number | null
  started_at?: string | null
  note?: string | null
}

const props = withDefaults(
  defineProps<{
    entries?: ModelAttributionEntry[]
    defaultOpen?: boolean
  }>(),
  {
    entries: () => [],
    defaultOpen: false,
  },
)

const { t } = useI18n()

const hasAnyMetrics = computed(() =>
  props.entries.some(
    (e) =>
      e.prompt_tokens != null ||
      e.completion_tokens != null ||
      e.latency_ms != null,
  ),
)

function formatLatency(ms?: number | null): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(2)} s`
}
</script>

<style scoped>
.report-provenance {
  margin: var(--s-4, 16px) 0;
  border: 1px solid var(--rule, #e2e8f0);
  border-radius: var(--r-1, 6px);
  padding: var(--s-2, 8px) var(--s-3, 12px);
  font-family: var(--ff-sans, system-ui);
  font-size: 13px;
  color: var(--fg-body, #1e293b);
  background: var(--bg-elevated, #fff);
}
.report-provenance__summary {
  cursor: pointer;
  font-weight: 600;
  user-select: none;
  padding: var(--s-1, 4px) 0;
}
.report-provenance__count {
  color: var(--fg-muted, #94a3b8);
  font-weight: 400;
  margin-left: 6px;
}
.report-provenance__table {
  width: 100%;
  border-collapse: collapse;
  margin-top: var(--s-2, 8px);
}
.report-provenance__table th,
.report-provenance__table td {
  text-align: left;
  padding: 6px 10px;
  border-bottom: 1px solid var(--rule, #e2e8f0);
}
.report-provenance__table th {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--fg-muted, #64748b);
}
.report-provenance__table td.num,
.report-provenance__table th.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.report-provenance__table td.model-id {
  font-family: var(--ff-mono, monospace);
  font-size: 12px;
}
.report-provenance__hint {
  margin: var(--s-2, 8px) 0 0;
  font-size: 12px;
  color: var(--fg-muted, #64748b);
  font-style: italic;
}
</style>
