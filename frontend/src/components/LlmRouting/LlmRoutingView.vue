<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue';
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
const providerModels = ref<Record<string, any[]>>({});

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
    const [p, r] = await Promise.all([
      listLlmProviders(),
      getRunLlmRouting(props.runId)
    ]);
    providers.value = p;
    routing.value = r.runtime_config;
    snapshots.value = r.snapshots;

    // Prefetch models for configured providers
    if (routing.value) {
      await fetchModelsFor(routing.value.default_route.provider_id);
      for (const stage of STAGES) {
        const override = routing.value.stage_overrides[stage];
        if (override) {
          await fetchModelsFor(override.provider_id);
        }
      }
    }
  } catch (e: any) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function fetchModelsFor(providerId: string) {
  if (providerModels.value[providerId]) return;
  try {
    const models = await listProviderModels(providerId);
    providerModels.value[providerId] = models;
  } catch (e) {
    console.warn(`Failed to fetch models for ${providerId}`, e);
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

const updateProvider = async (route: StageLLMRoute, providerId: string) => {
  route.provider_id = providerId;
  await fetchModelsFor(providerId);
};

const jsonOptions = computed({
  get: () => (route: StageLLMRoute) => JSON.stringify(route.provider_options, null, 2),
  set: (val: string) => (route: StageLLMRoute) => {
    try {
      route.provider_options = JSON.parse(val);
    } catch (e) {
      // Ignore invalid JSON during typing
    }
  }
});

function handleJsonInput(route: StageLLMRoute, event: Event) {
  const val = (event.target as HTMLTextAreaElement).value;
  try {
    route.provider_options = JSON.parse(val);
  } catch (e) {
    // wait for valid json
  }
}

</script>

<template>
  <div class="llm-routing-view">
    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-if="error" class="error">{{ error }}</div>

    <div v-if="routing" class="content-grid">
      <!-- Left: Global Config -->
      <div class="config-pane">
        <div class="header-with-version">
          <h3>{{ t('llm.routing.global_default') }}</h3>
          <span class="version-tag">{{ t('llm.routing.routing_version') }}: v{{ routing.routing_version }}</span>
        </div>

        <div class="card">
          <div class="field">
            <label>{{ t('llm.provider') }}</label>
            <select :value="routing.default_route.provider_id" @change="(e: any) => updateProvider(routing!.default_route, e.target.value)">
              <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </div>

          <div class="field">
            <label>{{ t('llm.model') }}</label>
            <div class="model-selection">
              <select v-model="routing.default_route.model">
                <option v-for="m in providerModels[routing.default_route.provider_id] || []" :key="m.id" :value="m.id">
                  {{ m.id }}
                </option>
                <option value="custom">{{ t('llm.routing.custom_model') }}</option>
              </select>
              <input v-if="routing.default_route.model === 'custom' || !(providerModels[routing.default_route.provider_id]?.find(m => m.id === routing!.default_route.model))"
                     v-model="routing.default_route.model" :placeholder="t('llm.routing.custom_model')" />
            </div>
            <div class="source-badges" v-if="providerModels[routing.default_route.provider_id]?.find(m => m.id === routing!.default_route.model)">
               <span class="badge" :class="providerModels[routing.default_route.provider_id].find(m => m.id === routing!.default_route.model).source">
                 {{ t(`llm.routing.source_badges.${providerModels[routing.default_route.provider_id].find(m => m.id === routing!.default_route.model).source}`) }}
               </span>
            </div>
          </div>

          <div class="field">
            <label>{{ t('llm.reasoning_effort') }}</label>
            <select v-model="routing.default_route.reasoning_effort">
              <option v-for="e in REASONING_EFFORTS" :key="e" :value="e">{{ e }}</option>
            </select>
          </div>

          <div class="field">
            <label>{{ t('llm.routing.provider_options') }}</label>
            <textarea class="json-editor" :value="JSON.stringify(routing.default_route.provider_options, null, 2)" @input="(e) => handleJsonInput(routing!.default_route, e)"></textarea>
          </div>

          <button class="primary-btn" @click="saveGlobal" :disabled="loading">{{ t('common.save') }}</button>
        </div>

        <h3>{{ t('llm.routing.stage_overrides') }}</h3>
        <div v-for="stage in STAGES" :key="stage" class="stage-row card" :class="{ locked: isStageLocked(stage) }">
          <div class="stage-header">
            <h4>{{ t(`llm.stages.${stage}`) }}</h4>
            <div v-if="isStageLocked(stage)" class="locked-badge">
               <span class="icon">🔒</span> {{ t('llm.routing.locked') }}
            </div>
          </div>

          <p v-if="isStageLocked(stage)" class="locked-hint">{{ t('llm.routing.locked_explanation') }}</p>

          <div class="stage-controls">
            <div class="field">
              <label>{{ t('llm.provider') }}</label>
              <select
                :value="routing.stage_overrides[stage]?.provider_id || routing.default_route.provider_id"
                @change="(e: any) => {
                  if (!routing) return;
                  if (!routing.stage_overrides[stage]) {
                    routing.stage_overrides[stage] = { ...routing.default_route };
                  }
                  updateProvider(routing.stage_overrides[stage], e.target.value);
                }"
                :disabled="isStageLocked(stage)"
              >
                <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
              </select>
            </div>

            <div class="field" v-if="routing.stage_overrides[stage]">
               <label>{{ t('llm.model') }}</label>
               <select v-model="routing.stage_overrides[stage].model" :disabled="isStageLocked(stage)">
                 <option v-for="m in providerModels[routing.stage_overrides[stage].provider_id] || []" :key="m.id" :value="m.id">
                    {{ m.id }}
                 </option>
                 <option value="custom">{{ t('llm.routing.custom_model') }}</option>
               </select>
            </div>

            <button
              v-if="routing.stage_overrides[stage]"
              @click="saveStage(stage, routing.stage_overrides[stage])"
              :disabled="loading || isStageLocked(stage)"
              class="apply-btn"
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
            <div class="snap-row">
              <span class="label">{{ t('llm.model') }}:</span>
              <span class="value">{{ snap.model }}</span>
            </div>
            <div class="snap-row">
              <span class="label">{{ t('llm.provider') }}:</span>
              <span class="value">{{ snap.provider_id }}</span>
            </div>
            <div v-if="routing.routing_version !== snap.routing_version" class="version-divergence">
               {{ t('llm.routing.version_divergence', { configured: routing.routing_version, active: snap.routing_version }) }}
            </div>
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
  background: white;
}
.field {
  margin-bottom: 1rem;
}
.field label {
  display: block;
  font-weight: bold;
  font-size: 0.85rem;
  margin-bottom: 0.25rem;
  color: #666;
}
.model-selection {
  display: flex;
  gap: 0.5rem;
}
.json-editor {
  width: 100%;
  min-height: 80px;
  font-family: monospace;
  font-size: 0.8rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  padding: 0.5rem;
}
.header-with-version {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.version-tag {
  font-size: 0.8rem;
  color: #999;
}
.badge {
  font-size: 0.7rem;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
}
.badge.live { background: #e3f2fd; color: #1976d2; }
.badge.cached { background: #f5f5f5; color: #616161; }
.badge.fallback { background: #fff3e0; color: #f57c00; }
.badge.custom { background: #f3e5f5; color: #7b1fa2; }

.primary-btn {
  background: #333;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
}
.apply-btn {
  background: #666;
  color: white;
  border: none;
  padding: 0.4rem 0.8rem;
  border-radius: 4px;
  cursor: pointer;
}
.locked-hint {
  font-size: 0.8rem;
  color: #666;
  font-style: italic;
  margin-bottom: 1rem;
}
.version-divergence {
  font-size: 0.75rem;
  color: #f57c00;
  margin-top: 0.5rem;
  font-weight: bold;
}
.snap-row {
  display: flex;
  gap: 0.5rem;
  font-size: 0.9rem;
  margin-bottom: 0.25rem;
}
.snap-row .label { color: #666; }
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
