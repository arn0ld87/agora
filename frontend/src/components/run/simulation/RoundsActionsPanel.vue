<script setup lang="ts">
/**
 * Aktionstabelle der Simulation (cursor-paginiert) mit Filtern nach Runde,
 * Netzwerk und Aktionsart. Die Filter stehen in der Query (`round`, `platform`,
 * `type`), die Adresse ist teilbar. `openPost` führt auf die Beitragsadresse.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { getSimulationActions } from '@/api/simulation'
import { readEnvelope, describeError } from '@/composables/run/simulation/simulationEnvelope'
import { SimActionPageSchema, SimActionTypeSchema, type SimActionPage, type SimActionType } from '@/contracts/simActionContract'
import type { Platform } from '@/contracts/postEventContract'
import SimActionsTable from '@/components/v4/sim-feed/SimActionsTable.vue'

const props = defineProps<{ simulationId: string; roundOptions: number[] }>()

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const ACTION_TYPES = SimActionTypeSchema.options as readonly SimActionType[]

const page = ref<SimActionPage>({ items: [], next_cursor: null })
const loading = ref(true)
const error = ref<string | null>(null)
let requestId = 0

function q(key: string): string | null {
  const v = route.query[key]
  return typeof v === 'string' && v !== '' ? v : null
}
const roundFilter = computed<number | null>(() => {
  const v = q('round')
  const n = v === null ? NaN : Number(v)
  return Number.isInteger(n) && n >= 0 ? n : null
})
const platformFilter = computed<Platform | null>(() => {
  const v = q('platform')
  return v === 'twitter' || v === 'reddit' ? v : null
})
const typeFilter = computed<SimActionType | null>(() => {
  const v = q('type')
  return v !== null && (ACTION_TYPES as readonly string[]).includes(v) ? (v as SimActionType) : null
})

function updateQuery(patch: Record<string, string | null>): void {
  const next: Record<string, string> = {}
  for (const [key, value] of Object.entries({ ...route.query, ...patch })) {
    if (typeof value === 'string' && value !== '') next[key] = value
  }
  void router.replace({ query: next })
}
function onSelect(key: string, event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  updateQuery({ [key]: value === '' ? null : value })
}

async function load(reset: boolean): Promise<void> {
  const id = ++requestId
  loading.value = true
  error.value = null
  try {
    const next = readEnvelope(
      await getSimulationActions(props.simulationId, {
        cursor: reset ? undefined : (page.value.next_cursor ?? undefined),
        round_num: roundFilter.value ?? undefined,
        platform: platformFilter.value ?? undefined,
        action_type: typeFilter.value ?? undefined,
      }),
      SimActionPageSchema,
      'GET /api/simulation/<id>/actions',
    )
    if (id !== requestId) return
    page.value = reset ? next : { items: [...page.value.items, ...next.items], next_cursor: next.next_cursor }
  } catch (err) {
    if (id === requestId) error.value = describeError(err)
  } finally {
    if (id === requestId) loading.value = false
  }
}

onMounted(() => void load(true))
watch([roundFilter, platformFilter, typeFilter], () => void load(true))

function openPost(postId: string): void {
  void router.push({ name: 'RunSimulationPost', params: { simulationId: props.simulationId, postId } })
}
</script>

<template>
  <div class="rap" data-testid="actions-panel">
    <div class="rap__filters">
      <label class="rap__field">
        <span>{{ t('views.run.simRounds.filterRound') }}</span>
        <select :value="roundFilter === null ? '' : String(roundFilter)" data-testid="filter-round" @change="onSelect('round', $event)">
          <option value="">{{ t('views.run.simRounds.filterAll') }}</option>
          <option v-for="n in roundOptions" :key="n" :value="String(n)">{{ n }}</option>
        </select>
      </label>
      <label class="rap__field">
        <span>{{ t('views.run.simRounds.filterNetwork') }}</span>
        <select :value="platformFilter ?? ''" data-testid="filter-platform" @change="onSelect('platform', $event)">
          <option value="">{{ t('views.run.simRounds.filterAll') }}</option>
          <option value="twitter">{{ t('views.run.simRounds.twitter') }}</option>
          <option value="reddit">{{ t('views.run.simRounds.reddit') }}</option>
        </select>
      </label>
      <label class="rap__field">
        <span>{{ t('views.run.simRounds.filterType') }}</span>
        <select :value="typeFilter ?? ''" data-testid="filter-type" @change="onSelect('type', $event)">
          <option value="">{{ t('views.run.simRounds.filterAll') }}</option>
          <option v-for="type in ACTION_TYPES" :key="type" :value="type">{{ t(`feed.actionType.${type}`) }}</option>
        </select>
      </label>
    </div>
    <div v-if="error" class="rap__error" role="alert" data-testid="actions-error">
      <span>{{ t('views.run.simRounds.actionsLoadError', { reason: error }) }}</span>
      <button type="button" class="rap__btn" @click="load(true)">{{ t('views.run.simRounds.retry') }}</button>
    </div>
    <SimActionsTable
      v-else
      :page="page"
      :loading="loading"
      :filters="{
        round: roundFilter ?? undefined,
        platform: platformFilter ?? undefined,
        actionType: typeFilter ?? undefined,
      }"
      @load-more="load(false)"
      @open-post="openPost"
    />
  </div>
</template>

<style scoped>
.rap__filters { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; }
.rap__field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--fg2); }
.rap__field select {
  height: 32px; padding: 0 10px; border: none; border-radius: var(--ag-r-8);
  background: var(--field); color: var(--fg); font: inherit; font-size: 13px;
}
.rap__field select:focus-visible, .rap__btn:focus-visible { outline: 2px solid var(--acc-line); outline-offset: 2px; }
.rap__error {
  display: flex; align-items: center; gap: 12px; padding: 10px 12px;
  border-radius: var(--ag-r-8); background: var(--err-soft); color: var(--err); font-size: 13px;
}
.rap__btn {
  height: 28px; padding: 0 10px; border: 1px solid currentColor; border-radius: var(--ag-r-6);
  background: transparent; color: inherit; font: inherit; font-size: 12px; cursor: pointer;
}
</style>
