<script setup lang="ts">
/**
 * Runden der Simulation: eine Zeile je Runde mit Aktivität je Netzwerk und
 * Sprung in den Feed an dieser Runde. `round_num` ist 1-basiert, Runde 0 sind
 * die Startbeiträge (backend/scripts/sim_runtime/platform_runner.py).
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { RoundSummary } from '@/contracts/simActionContract'
import { SimActionTypeSchema } from '@/contracts/simActionContract'

type Network = 'twitter' | 'reddit'

const props = defineProps<{
  simulationId: string
  rounds: RoundSummary[]
  loading: boolean
  error: string | null
  /** Aktuelle Runde laut Laufstand; `null` = unbekannt. */
  currentRound: number | null
  totalRounds: number | null
  running: boolean
}>()
const emit = defineEmits<{ retry: [] }>()

const { t } = useI18n()
const KNOWN = SimActionTypeSchema.options as readonly string[]

interface Row {
  roundNum: number
  networks: { network: Network; counts: { key: string; count: number }[] }[]
}

const rows = computed<Row[]>(() => {
  const map = new Map<number, Row>()
  for (const entry of props.rounds) {
    const row = map.get(entry.round_num) ?? { roundNum: entry.round_num, networks: [] }
    map.set(entry.round_num, row)
    const counts = Object.entries(entry.action_counts)
      .filter(([, n]) => n > 0)
      .sort(([a], [b]) => {
        const ia = KNOWN.indexOf(a)
        const ib = KNOWN.indexOf(b)
        return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib)
      })
      .map(([key, count]) => ({ key, count }))
    row.networks.push({ network: entry.platform as Network, counts })
  }
  for (const row of map.values()) row.networks.sort((a, b) => a.network.localeCompare(b.network))
  return [...map.values()].sort((a, b) => a.roundNum - b.roundNum)
})

function roundTitle(n: number): string {
  if (n === 0) return t('views.run.simRounds.startRound')
  if (props.totalRounds && props.totalRounds > 0) {
    return t('views.run.simRounds.roundOf', { round: n, total: props.totalRounds })
  }
  return t('views.run.simRounds.round', { round: n })
}
function isCurrent(n: number): boolean {
  return props.running && props.currentRound !== null && n === props.currentRound
}
function networkLabel(n: Network): string {
  return t(`views.run.simRounds.${n}`)
}
function actionLabel(key: string): string {
  return KNOWN.includes(key) ? t(`feed.actionType.${key}`) : key
}
function feedTarget(roundNum: number, network?: Network) {
  return {
    name: 'RunSimulationFeed',
    params: network ? { simulationId: props.simulationId, network } : { simulationId: props.simulationId },
    query: { round: String(roundNum) },
  }
}
</script>

<template>
  <div class="rl" data-testid="rounds-list">
    <p v-if="loading" class="rl__meta" role="status" aria-busy="true">{{ t('views.run.simRounds.loading') }}</p>
    <div v-else-if="error" class="rl__error" role="alert" data-testid="rounds-error">
      <span>{{ t('views.run.simRounds.error', { reason: error }) }}</span>
      <button type="button" class="rl__btn" @click="emit('retry')">{{ t('views.run.simRounds.retry') }}</button>
    </div>
    <p v-else-if="rows.length === 0" class="rl__meta" role="status" data-testid="rounds-empty">
      {{ t('views.run.simRounds.empty') }}
    </p>
    <ol v-else class="rl__list">
      <li
        v-for="row in rows"
        :key="row.roundNum"
        class="rl__row"
        :class="{ 'rl__row--current': isCurrent(row.roundNum) }"
        :aria-current="isCurrent(row.roundNum) ? 'step' : undefined"
        :data-testid="`round-${row.roundNum}`"
      >
        <div class="rl__head">
          <h3 class="rl__title">{{ roundTitle(row.roundNum) }}</h3>
          <span v-if="isCurrent(row.roundNum)" class="rl__badge">{{ t('views.run.simRounds.running') }}</span>
        </div>
        <ul class="rl__networks">
          <li v-for="net in row.networks" :key="net.network" class="rl__network">
            <span class="rl__netname">{{ networkLabel(net.network) }}</span>
            <span v-if="net.counts.length === 0" class="rl__count">{{ t('views.run.simRounds.noActions') }}</span>
            <span v-for="c in net.counts" :key="c.key" class="rl__count">{{ actionLabel(c.key) }}: {{ c.count }}</span>
            <router-link
              class="rl__link"
              :to="feedTarget(row.roundNum, net.network)"
              :aria-label="t('views.run.simRounds.openFeedForNetwork', { round: row.roundNum, network: networkLabel(net.network) })"
              :data-testid="`round-${row.roundNum}-feed-${net.network}`"
            >{{ t('views.run.simRounds.openFeed') }}</router-link>
          </li>
        </ul>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.rl__meta { margin: 0; padding: 24px 0; color: var(--fg3); font-size: 13px; }
.rl__error {
  display: flex; align-items: center; gap: 12px; padding: 10px 12px;
  border-radius: var(--ag-r-8); background: var(--err-soft); color: var(--err); font-size: 13px;
}
.rl__btn {
  height: 28px; padding: 0 10px; border: 1px solid currentColor; border-radius: var(--ag-r-6);
  background: transparent; color: inherit; font: inherit; font-size: 12px; cursor: pointer;
}
.rl__btn:focus-visible, .rl__link:focus-visible { outline: 2px solid var(--acc-line); outline-offset: 2px; }
.rl__list { list-style: none; margin: 0; padding: 0; }
.rl__row { padding: 10px 12px; border-top: 1px solid var(--line); }
.rl__row:first-child { border-top: none; }
.rl__row--current { background: var(--s2); border-radius: var(--ag-r-8); }
.rl__head { display: flex; align-items: center; gap: 8px; }
.rl__title { margin: 0; font-size: 14px; font-weight: 650; color: var(--fg); }
.rl__badge { padding: 1px 8px; border-radius: var(--ag-r-6); background: var(--s3); color: var(--fg2); font-size: 12px; }
.rl__networks { list-style: none; margin: 6px 0 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.rl__network { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; font-size: 12px; }
.rl__netname { font-weight: 600; color: var(--fg2); min-width: 56px; }
.rl__count { color: var(--fg3); }
.rl__link { margin-left: auto; color: var(--acc-text); text-decoration: none; font-size: 12px; }
.rl__link:hover { text-decoration: underline; }
</style>
