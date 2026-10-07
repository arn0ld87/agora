<script setup lang="ts">
/**
 * Runden der Simulation am Lauf (Etappe 4, #1801, Bauplan 4.5): Umschalter
 * „Runden | Aktionen“ (Query `?view=actions`), Rundenliste mit Aktivität je
 * Netzwerk und Sprung in den Feed, dazu die Aktionstabelle.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { getSimulationRounds } from '@/api/simulation'
import { readEnvelope, describeError } from '@/composables/run/simulation/simulationEnvelope'
import { useSimulationRunStateContext } from '@/composables/run/simulation/useSimulationRunStateContext'
import { RoundsResponseSchema, type RoundSummary } from '@/contracts/simActionContract'
import RoundsActionsToggle, { type RoundsView } from '@/components/run/simulation/RoundsActionsToggle.vue'
import RoundsList from '@/components/run/simulation/RoundsList.vue'
import RoundsActionsPanel from '@/components/run/simulation/RoundsActionsPanel.vue'

const props = defineProps<{ simulationId: string }>()
const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const state = useSimulationRunStateContext(() => props.simulationId)

const view = computed<RoundsView>(() => (route.query.view === 'actions' ? 'actions' : 'rounds'))
function setView(next: RoundsView): void {
  const query: Record<string, string> = {}
  for (const [key, value] of Object.entries(route.query)) {
    if (typeof value === 'string' && value !== '' && key !== 'view') query[key] = value
  }
  if (next === 'actions') query.view = 'actions'
  void router.replace({ query })
}

const rounds = ref<RoundSummary[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
let requestId = 0

async function loadRounds(): Promise<void> {
  const id = ++requestId
  loading.value = true
  error.value = null
  try {
    const data = readEnvelope(await getSimulationRounds(props.simulationId), RoundsResponseSchema, 'GET /api/simulation/<id>/rounds')
    if (id === requestId) rounds.value = data.rounds
  } catch (err) {
    if (id === requestId) error.value = describeError(err)
  } finally {
    if (id === requestId) loading.value = false
  }
}
onMounted(() => void loadRounds())
watch(() => props.simulationId, () => void loadRounds())

// Läuft die Simulation, wächst die Liste: bei neuer Runde nachladen.
watch(() => state.currentRound.value, () => {
  if (state.stateKind.value === 'running') void loadRounds()
})

const running = computed(() => state.stateKind.value === 'running' || state.stateKind.value === 'queued')
const roundOptions = computed(() => [...new Set(rounds.value.map((r) => r.round_num))].sort((a, b) => a - b))
</script>

<template>
  <section class="rsv" data-testid="run-sim-rounds">
    <header class="rsv__head">
      <h2 class="rsv__title">{{ t('views.run.simRounds.title') }}</h2>
      <RoundsActionsToggle :model-value="view" @update:model-value="setView" />
    </header>
    <RoundsList
      v-if="view === 'rounds'"
      :simulation-id="simulationId"
      :rounds="rounds"
      :loading="loading"
      :error="error"
      :current-round="state.currentRound.value"
      :total-rounds="state.totalRounds.value"
      :running="running"
      @retry="loadRounds"
    />
    <RoundsActionsPanel v-else :simulation-id="simulationId" :round-options="roundOptions" />
  </section>
</template>

<style scoped>
.rsv { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.rsv__head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.rsv__title { margin: 0; font-size: 16px; font-weight: 650; color: var(--fg); }
</style>
