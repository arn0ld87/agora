<script setup>
import { computed, ref, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { createSimulation } from '../api/simulation'
import Btn from './ui/Btn.vue'
import Badge from './ui/Badge.vue'
import Kicker from './ui/Kicker.vue'

const router = useRouter()
const { t } = useI18n()

const props = defineProps({
  currentPhase: { type: Number, default: 0 },
  projectData: Object,
  ontologyProgress: Object,
  buildProgress: Object,
  graphData: Object,
  systemLogs: { type: Array, default: () => [] }
})

defineEmits(['next-step'])

const selectedItem = ref(null)
const logContent = ref(null)
const creatingSimulation = ref(false)

const graphStats = computed(() => {
  const nodes = props.graphData?.node_count || props.graphData?.nodes?.length || 0
  const edges = props.graphData?.edge_count || props.graphData?.edges?.length || 0
  const types = props.projectData?.ontology?.entity_types?.length || 0
  return { nodes, edges, types }
})

function selectItem(item, type) {
  selectedItem.value = { ...item, itemType: type }
}

async function enterEnvSetup() {
  if (!props.projectData?.project_id || !props.projectData?.graph_id) return
  creatingSimulation.value = true
  try {
    const res = await createSimulation({
      project_id: props.projectData.project_id,
      graph_id: props.projectData.graph_id,
      enable_twitter: true,
      enable_reddit: true
    })
    if (res.success && res.data?.simulation_id) {
      router.push({ name: 'Simulation', params: { simulationId: res.data.simulation_id } })
    } else {
      alert(t('errors.unknown') + ': ' + (res.error || ''))
    }
  } catch (err) {
    alert(t('errors.unknown') + ': ' + err.message)
  } finally {
    creatingSimulation.value = false
  }
}

watch(() => props.systemLogs.length, () => {
  nextTick(() => {
    if (logContent.value) logContent.value.scrollTop = logContent.value.scrollHeight
  })
})

function phaseLabel(phase) {
  if (props.currentPhase > phase) return t('common.completed')
  if (props.currentPhase === phase) return t('common.running')
  return t('common.ready')
}

function phaseVariant(phase) {
  if (props.currentPhase > phase) return 'solid'
  if (props.currentPhase === phase) return 'accent'
  return 'outline'
}
</script>

<template>
  <div class="step-panel">
    <div class="scroll">

      <!-- Card 1: Ontology -->
      <article class="card" :class="{ 'is-active': currentPhase === 0 }">
        <header class="card-head">
          <Kicker num="01">{{ t('step1.ontology.title') }}</Kicker>
          <Badge :variant="phaseVariant(0)" :dot="currentPhase === 0">{{ phaseLabel(0) }}</Badge>
        </header>
        <p class="card-desc">{{ t('step1.ontology.desc') }}</p>

        <div v-if="currentPhase === 0 && ontologyProgress" class="progress-row">
          <span class="spinner-sm" />
          <span>{{ ontologyProgress.message || t('common.processing') }}</span>
        </div>

        <div v-if="selectedItem" class="detail-overlay">
          <div class="detail-head">
            <div>
              <Badge variant="ghost">{{ selectedItem.itemType === 'entity' ? 'ENTITY' : 'RELATION' }}</Badge>
              <span class="detail-name">{{ selectedItem.name }}</span>
            </div>
            <button class="x" @click="selectedItem = null" aria-label="×">×</button>
          </div>
          <p class="detail-desc">{{ selectedItem.description }}</p>
          <div v-if="selectedItem.attributes?.length" class="detail-section">
            <Kicker>{{ t('step1.ontology.title') }}</Kicker>
            <ul>
              <li v-for="a in selectedItem.attributes" :key="a.name">
                <strong>{{ a.name }}</strong> <span class="meta">({{ a.type }})</span> — {{ a.description }}
              </li>
            </ul>
          </div>
          <div v-if="selectedItem.examples?.length" class="detail-section">
            <Kicker>EXAMPLES</Kicker>
            <div class="chips">
              <span v-for="ex in selectedItem.examples" :key="ex" class="chip">{{ ex }}</span>
            </div>
          </div>
          <div v-if="selectedItem.source_targets?.length" class="detail-section">
            <Kicker>CONNECTIONS</Kicker>
            <ul>
              <li v-for="(c, i) in selectedItem.source_targets" :key="i">
                {{ c.source }} → {{ c.target }}
              </li>
            </ul>
          </div>
        </div>

        <div v-if="projectData?.ontology?.entity_types && !selectedItem" class="chips-block">
          <Kicker>ENTITÄTSTYPEN</Kicker>
          <div class="chips">
            <button
              v-for="entity in projectData.ontology.entity_types"
              :key="entity.name"
              class="chip clickable"
              @click="selectItem(entity, 'entity')"
            >{{ entity.name }}</button>
          </div>
        </div>
        <div v-if="projectData?.ontology?.edge_types && !selectedItem" class="chips-block">
          <Kicker>RELATIONSTYPEN</Kicker>
          <div class="chips">
            <button
              v-for="rel in projectData.ontology.edge_types"
              :key="rel.name"
              class="chip clickable"
              @click="selectItem(rel, 'relation')"
            >{{ rel.name }}</button>
          </div>
        </div>
      </article>

      <!-- Card 2: Graph build -->
      <article class="card" :class="{ 'is-active': currentPhase === 1 }">
        <header class="card-head">
          <Kicker num="02">{{ t('step1.build.title') }}</Kicker>
          <Badge :variant="phaseVariant(1)" :dot="currentPhase === 1">
            <template v-if="currentPhase === 1">{{ buildProgress?.progress || 0 }} %</template>
            <template v-else>{{ phaseLabel(1) }}</template>
          </Badge>
        </header>
        <p class="card-desc">{{ t('step1.build.desc') }}</p>
        <div class="stats-grid">
          <div class="stat">
            <span class="stat-value">{{ graphStats.nodes }}</span>
            <span class="stat-label">{{ t('step1.graph.nodes') }}</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ graphStats.edges }}</span>
            <span class="stat-label">{{ t('step1.graph.edges') }}</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ graphStats.types }}</span>
            <span class="stat-label">ENTITÄTSTYPEN</span>
          </div>
        </div>
        <div v-if="currentPhase === 1 && buildProgress?.message" class="progress-row">
          <span class="spinner-sm" />
          <span>{{ buildProgress.message }}</span>
        </div>
      </article>

      <!-- Card 3: Done → next -->
      <article class="card" :class="{ 'is-active': currentPhase >= 2 }">
        <header class="card-head">
          <Kicker num="03" accent>{{ t('step1.next') }}</Kicker>
          <Badge :variant="currentPhase >= 2 ? 'accent' : 'outline'" :dot="currentPhase >= 2">
            {{ currentPhase >= 2 ? t('common.ready') : t('common.loading') }}
          </Badge>
        </header>
        <p class="card-desc">{{ t('step1.build.completed') }}</p>
        <Btn
          variant="primary"
          arrow
          :disabled="currentPhase < 2 || creatingSimulation"
          :loading="creatingSimulation"
          @click="enterEnvSetup"
        >
          {{ t('step1.next') }}
        </Btn>
      </article>
    </div>

    <!-- Logs strip -->
    <aside class="logs">
      <div class="logs-head">
        <Kicker>System</Kicker>
        <span class="meta">{{ projectData?.project_id || 'NO_PROJECT' }}</span>
      </div>
      <div ref="logContent" class="logs-body log-block">
        <div v-for="(log, idx) in systemLogs" :key="idx" class="log-line">
          <span class="ts">{{ log.time }}</span> · {{ log.msg }}
        </div>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.step-panel {
  height: 100%;
  background: var(--paper-0);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.scroll {
  flex: 1;
  overflow-y: auto;
  padding: var(--s-6);
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
}

.card {
  background: var(--paper-0);
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  padding: var(--s-5);
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}
.card.is-active { border-color: var(--accent); }
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--rule);
  padding-bottom: var(--s-3);
}
.card-desc {
  font-family: var(--ff-sans);
  color: var(--fg-body);
  font-size: var(--fs-16);
  margin: 0;
}
.progress-row {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  color: var(--fg-muted);
}
.spinner-sm {
  width: 12px; height: 12px;
  border: 1.5px solid var(--accent);
  border-top-color: transparent;
  border-radius: 50%;
  animation: sp 0.7s linear infinite;
  display: inline-block;
}
@keyframes sp { to { transform: rotate(360deg); } }

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border-top: 1px solid var(--rule);
}
.stat {
  padding: var(--s-3) var(--s-3) var(--s-3) 0;
  border-right: 1px solid var(--rule);
}
.stat:last-child { border-right: 0; }
.stat-value {
  display: block;
  font-family: var(--ff-serif);
  font-size: var(--fs-32);
  color: var(--ink-0);
  line-height: 1;
}
.stat-label {
  display: block;
  margin-top: var(--s-2);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}

.chips-block { display: flex; flex-direction: column; gap: var(--s-2); }
.chips { display: flex; flex-wrap: wrap; gap: var(--s-2); }
.chip {
  display: inline-block;
  padding: 4px 10px;
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  letter-spacing: 0.04em;
  border: 1px solid var(--rule-strong);
  background: transparent;
  color: var(--ink-0);
  border-radius: var(--r-pill);
}
.chip.clickable { cursor: pointer; transition: background 150ms ease; }
.chip.clickable:hover { background: var(--paper-1); }

.detail-overlay {
  background: var(--paper-1);
  border-left: 2px solid var(--accent);
  padding: var(--s-4);
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.detail-head { display: flex; justify-content: space-between; align-items: center; gap: var(--s-3); }
.detail-name {
  font-family: var(--ff-serif);
  font-size: var(--fs-20);
  color: var(--ink-0);
  margin-left: var(--s-2);
}
.detail-desc { color: var(--fg-body); margin: 0; }
.detail-section { display: flex; flex-direction: column; gap: var(--s-2); }
.detail-section ul { list-style: none; padding-left: 0; margin: 0; display: flex; flex-direction: column; gap: var(--s-2); font-family: var(--ff-sans); font-size: var(--fs-14); }
.detail-section li { color: var(--fg-body); }
.detail-section li strong { color: var(--ink-0); }
.x {
  background: transparent;
  border: 0;
  font-size: 22px;
  cursor: pointer;
  color: var(--fg-muted);
  line-height: 1;
}
.x:hover { color: var(--accent); }

.logs {
  border-top: 1px solid var(--rule-strong);
  padding: var(--s-4) var(--s-6);
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  background: var(--paper-0);
}
.logs-head { display: flex; justify-content: space-between; align-items: baseline; }
.logs-body {
  max-height: 140px;
  font-size: 11px;
}
.log-line { white-space: pre-wrap; }
</style>
