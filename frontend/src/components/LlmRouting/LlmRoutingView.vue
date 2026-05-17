<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  getRunLlmRouting,
  updateRunLlmRouting,
  patchStageLlmRouting,
} from '../../api/llmRouting';
import {
  RuntimeLlmRouting,
  StageLLMRoute,
  StageId,
  ReasoningEffort,
  LlmInvocationEvent,
} from '../../contracts/llmRoutingContract';
import ModelPicker from '@/components/v4/forms/ModelPicker.vue';
import { useLlmProvidersStore } from '@/store/llmProviders';

const props = defineProps<{
  runId: string;
}>();

const { t } = useI18n();

const providersStore = useLlmProvidersStore();
const routing = ref<RuntimeLlmRouting | null>(null);
const snapshots = ref<Record<string, any>>({});
const invocationEvents = ref<LlmInvocationEvent[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const STAGES: StageId[] = [
  "document_ingest",
  "ontology_generation",
  "graph_build",
  "persona_generation",
  "simulation_rounds",
  "report_generation",
  "evaluation",
];

const REASONING_EFFORTS: ReasoningEffort[] = ["none", "minimal", "low", "medium", "high"];

async function load() {
  loading.value = true;
  try {
    const [r] = await Promise.all([
      getRunLlmRouting(props.runId),
      providersStore.loadProviders(),
    ]);
    routing.value = r.runtime_config;
    snapshots.value = r.snapshots;
    invocationEvents.value = [...(r.invocation_events || [])].reverse();
  } catch (e: any) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

onMounted(load);

async function saveGlobal() {
  if (!routing.value) return;
  try {
    loading.value = true;
    routing.value = await updateRunLlmRouting(props.runId, routing.value);
  } catch (e: any) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function saveStage(stageId: StageId, route: StageLLMRoute) {
  try {
    loading.value = true;
    routing.value = await patchStageLlmRouting(props.runId, stageId, route);
  } catch (e: any) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

const isStageLocked = (stageId: string) => !!snapshots.value[stageId];
const formatLatency = (latencyMs: number) => `${Math.round(latencyMs)} ms`;
const formatTimestamp = (timestamp: number) => new Date(timestamp * 1000).toLocaleString();

function onGlobalDefaultPicked(route: StageLLMRoute | null) {
  if (!routing.value || !route) return;
  routing.value.global_default.provider_id = route.provider_id;
  routing.value.global_default.model = route.model;
}

function onStageOverridePicked(stageId: StageId, route: StageLLMRoute | null) {
  if (!routing.value || !route) return;
  const current = routing.value.stage_overrides[stageId];
  const base = current ? { ...current } : { ...routing.value.global_default };
  routing.value.stage_overrides[stageId] = {
    ...base,
    provider_id: route.provider_id,
    model: route.model,
  };
}

</script>

<template>
  <div class="llm-routing-view">
    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-if="error" class="error">{{ error }}</div>

    <div v-if="routing" class="content-grid">
      <!-- Left: Global Config -->
      <div class="config-pane">
        <h3>{{ t('llm.routing.global_default') }}</h3>
        <div class="card">
          <label>{{ t('llm.model') }}</label>
          <ModelPicker
            :model-value="routing.global_default"
            :placeholder="t('llm.routing.model_placeholder', 'Modell wählen …')"
            @update:model-value="onGlobalDefaultPicked"
          />

          <label>{{ t('llm.reasoning_effort') }}</label>
          <select v-model="routing.global_default.reasoning_effort">
            <option v-for="e in REASONING_EFFORTS" :key="e" :value="e">{{ e }}</option>
          </select>

          <button @click="saveGlobal" :disabled="loading">{{ t('common.save') }}</button>
        </div>

        <h3>{{ t('llm.routing.stage_overrides') }}</h3>
        <div v-for="stage in STAGES" :key="stage" class="stage-row card" :class="{ locked: isStageLocked(stage) }">
          <h4>{{ t(`llm.stages.${stage}`) }}</h4>
          <div v-if="isStageLocked(stage)" class="locked-badge">
             <span class="icon">🔒</span> {{ t('llm.routing.locked') }}
          </div>

          <div class="stage-controls">
            <label>{{ t('llm.model') }}</label>
            <ModelPicker
              :model-value="routing.stage_overrides[stage] || routing.global_default"
              :disabled="isStageLocked(stage)"
              :placeholder="t('llm.routing.model_placeholder', 'Modell wählen …')"
              @update:model-value="(route) => onStageOverridePicked(stage, route)"
            />

            <button
              v-if="routing.stage_overrides[stage]"
              @click="saveStage(stage, routing.stage_overrides[stage])"
              :disabled="loading || isStageLocked(stage)"
            >
              {{ t('common.apply') }}
            </button>
          </div>
        </div>
      </div>

      <!-- Right: Runtime Transparency -->
      <div class="status-pane">
        <h3>{{ t('llm.routing.active_snapshots') }}</h3>
        <div v-if="Object.keys(snapshots).length === 0" class="empty-hint">
          {{ t('llm.routing.no_snapshots_yet') }}
        </div>
        <div v-for="(snap, stageId) in snapshots" :key="stageId" class="snapshot-card card">
          <div class="snap-header">
            <strong>{{ t(`llm.stages.${stageId}`) }}</strong>
            <span class="version">v{{ snap.routing_version }}</span>
          </div>
          <div class="snap-body">
            <p><strong>{{ t('llm.model') }}:</strong> {{ snap.model }}</p>
            <p><strong>{{ t('llm.provider') }}:</strong> {{ snap.provider_id }}</p>
            <p class="timestamp">{{ snap.started_at }}</p>
          </div>
        </div>

        <h3>{{ t('llm.routing.call_events') }}</h3>
        <div v-if="invocationEvents.length === 0" class="empty-hint">
          {{ t('llm.routing.no_call_events_yet') }}
        </div>
        <div v-for="(event, index) in invocationEvents" :key="`${event.timestamp}-${index}`" class="snapshot-card card">
          <div class="snap-header">
            <strong>{{ event.stage }}</strong>
            <span class="version" :class="event.success ? 'version--ok' : 'version--error'">
              {{ event.success ? t('llm.routing.success') : t('llm.routing.failed') }}
            </span>
          </div>
          <div class="snap-body">
            <p><strong>{{ t('llm.model') }}:</strong> {{ event.model }}</p>
            <p><strong>{{ t('llm.provider') }}:</strong> {{ event.provider_id }}</p>
            <p><strong>{{ t('llm.routing.latency') }}:</strong> {{ formatLatency(event.latency_ms) }}</p>
            <p v-if="event.error_type"><strong>{{ t('llm.routing.error_type') }}:</strong> {{ event.error_type }}</p>
            <p class="timestamp">{{ formatTimestamp(event.timestamp) }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2rem;
}
.card {
  border: 1px solid #ddd;
  padding: 1rem;
  margin-bottom: 1rem;
  border-radius: 4px;
}
.locked {
  background-color: #f5f5f5;
  opacity: 0.8;
}
.locked-badge {
  color: #666;
  font-size: 0.8rem;
  margin-bottom: 0.5rem;
}
.snapshot-card .snap-header {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px solid #eee;
  padding-bottom: 0.5rem;
  margin-bottom: 0.5rem;
}
.version {
  background: #eee;
  padding: 2px 6px;
  border-radius: 10px;
  font-size: 0.7rem;
}
.version--ok {
  background: #dcfce7;
  color: #166534;
}
.version--error {
  background: #fee2e2;
  color: #991b1b;
}
.timestamp {
  font-size: 0.7rem;
  color: #999;
}
</style>
