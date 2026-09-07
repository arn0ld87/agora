<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import SettingsOverlay from '@/components/v4/forms/SettingsOverlay.vue'
import Card from '@/components/v4/forms/Card.vue'
import Field from '@/components/v4/forms/Field.vue'
import Input from '@/components/v4/forms/Input.vue'
import Select from '@/components/v4/forms/Select.vue'
import RunLlmRoutingPanel from '@/components/LlmRouting/LlmRoutingView.vue'
import { LlmRoutingTestId } from '@/contracts/testIds'
import { listRuns } from '@/api/runs'
import type { RunRecord } from '@/types/run'
import type { RunDetail } from '@/contracts/runsContract'

// Settings is only an entrypoint; routing persistence remains bound to real run IDs.
const SELECTED_RUN_STORAGE_KEY = 'agora.llmRouting.selectedRunId'
const { t } = useI18n()

// Issue #580: listRuns now returns RunsListResponse; use RunDetail for the item type.
const runs = ref<RunDetail[]>([])
const selectedRunId = ref(readStoredRunId())
const loadingRuns = ref(false)
const error = ref<string | null>(null)

const selectedRunIdTrimmed = computed(() => selectedRunId.value.trim())
const runOptions = computed(() =>
  runs.value.map((run) => ({
    value: run.run_id,
    label: `${run.run_id} · ${run.status}`,
  })),
)

function readStoredRunId(): string {
  if (typeof window === 'undefined' || !window.localStorage?.getItem) return ''
  return window.localStorage.getItem(SELECTED_RUN_STORAGE_KEY) || ''
}

function rememberRunId(runId: string): void {
  if (typeof window === 'undefined' || !window.localStorage?.setItem) return
  const trimmed = runId.trim()
  if (trimmed) {
    window.localStorage.setItem(SELECTED_RUN_STORAGE_KEY, trimmed)
  }
}

async function loadRuns(): Promise<void> {
  loadingRuns.value = true
  error.value = null
  try {
    const response = await listRuns({ limit: 25 })
    // Issue #580: data is RunsListResponse { runs, total, aggregation }
    runs.value = response.data?.runs || []
    if (!selectedRunIdTrimmed.value && runs.value.length > 0) {
      selectedRunId.value = runs.value[0].run_id
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : t('settings.v4.llmRouting.errors.loadRuns')
  } finally {
    loadingRuns.value = false
  }
}

watch(selectedRunIdTrimmed, (runId) => {
  rememberRunId(runId)
})

onMounted(() => {
  void loadRuns()
})
</script>

<template>
  <AppShell>
    <SettingsOverlay>
      <PageHeader
        :title="t('settings.v4.llmRouting.title')"
        :subtitle="t('settings.v4.llmRouting.subtitle')"
      />

      <Card
        :title="t('settings.v4.llmRouting.runSelectionTitle')"
        :subtitle="t('settings.v4.llmRouting.runSelectionSubtitle')"
      >
        <div class="run-picker">
          <Field :label="t('settings.v4.llmRouting.currentRunsLabel')">
            <Select
              v-model="selectedRunId"
              :options="runOptions"
              :disabled="loadingRuns || runOptions.length === 0"
              :placeholder="t('settings.v4.llmRouting.runSelectPlaceholder')"
            />
          </Field>

          <Field :label="t('settings.v4.llmRouting.runIdLabel')">
            <Input
              v-model="selectedRunId"
              mono
              :data-testid="LlmRoutingTestId.runId"
              placeholder="run_..."
            />
          </Field>

          <button
            class="llmr-btn llmr-btn--secondary"
            type="button"
            :disabled="loadingRuns"
            @click="loadRuns"
          >
            {{ t('settings.v4.llmRouting.refresh') }}
          </button>
        </div>

        <p v-if="error" class="llmr-error">{{ error }}</p>
      </Card>

      <div v-if="selectedRunIdTrimmed" class="routing-panel">
        <RunLlmRoutingPanel
          :key="selectedRunIdTrimmed"
          :run-id="selectedRunIdTrimmed"
        />
      </div>

      <Card
        v-else
        class="routing-empty"
        :title="t('settings.v4.llmRouting.emptyTitle')"
        :subtitle="t('settings.v4.llmRouting.emptySubtitle')"
      />
    </SettingsOverlay>
  </AppShell>
</template>

<style scoped>
.run-picker {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(220px, 1fr) auto;
  gap: 14px;
  align-items: end;
}

.routing-panel {
  margin-top: 20px;
}

.routing-empty {
  margin-top: 20px;
}

.llmr-error {
  margin: 12px 0 0;
  color: var(--status-red);
  font-family: var(--font-sans);
  font-size: 13px;
}

.llmr-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 36px;
  padding: 0 16px;
  border-radius: var(--r-3);
  font-family: var(--font-sans);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 120ms ease, border-color 120ms ease, opacity 120ms ease;
}

.llmr-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.llmr-btn--secondary {
  background: var(--surface-elevated);
  color: var(--text-primary);
  border-color: var(--hairline);
}

.llmr-btn--secondary:hover:not(:disabled) {
  background: var(--surface-inset);
}

@media (max-width: 820px) {
  .run-picker {
    grid-template-columns: 1fr;
  }
}
</style>
