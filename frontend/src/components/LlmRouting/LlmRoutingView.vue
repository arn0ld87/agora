<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  listLlmProviders,
  getRunLlmRouting,
  updateRunLlmRouting,
  patchStageLlmRouting,
  listProviderModels
} from '../../api/llmRouting';
import {
  ProviderDescriptor,
  RuntimeLlmRouting,
  StageLLMRoute,
  StageId,
  ReasoningEffort
} from '../../contracts/llmRoutingContract';

const props = defineProps<{
  runId: string;
}>();

const { t } = useI18n();

const providers = ref<ProviderDescriptor[]>([]);
const routing = ref<RuntimeLlmRouting | null>(null);
const snapshots = ref<Record<string, any>>({});
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
  loading.ref = true;
  try {
    const [p, r] = await Promise.all([
      listLlmProviders(),
      getRunLlmRouting(props.runId)
    ]);
    providers.value = p;
    routing.value = r.runtime_config;
    snapshots.value = r.snapshots;
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

function getProvider(id: string) {
  return providers.value.find(p => p.id === id);
}

const isStageLocked = (stageId: string) => !!snapshots.value[stageId];

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
          <label>{{ t('llm.provider') }}</label>
          <select v-model="routing.default_route.provider_id">
            <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>

          <label>{{ t('llm.model') }}</label>
          <input v-model="routing.default_route.model" />

          <label>{{ t('llm.reasoning_effort') }}</label>
          <select v-model="routing.default_route.reasoning_effort">
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
            <label>{{ t('llm.provider') }}</label>
            <select
              :value="routing.stage_overrides[stage]?.provider_id || routing.default_route.provider_id"
              @change="(e: any) => {
                if (!routing) return;
                if (!routing.stage_overrides[stage]) {
                  routing.stage_overrides[stage] = { ...routing.default_route };
                }
                routing.stage_overrides[stage].provider_id = e.target.value;
              }"
              :disabled="isStageLocked(stage)"
            >
              <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>

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
.timestamp {
  font-size: 0.7rem;
  color: #999;
}
</style>
