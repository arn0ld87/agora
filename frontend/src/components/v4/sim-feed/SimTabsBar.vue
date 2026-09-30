<script setup lang="ts">
/**
 * SimTabsBar — Tabsleiste unterhalb des PipelineStepper.
 *
 * Slice UI-2b (#1713), docs/design/simulation-feed.md §2.1. Ersetzt die
 * bisherige `Tabs`-Instanz (`sim-view-tabs`) in SimulationLayout.vue für die
 * fünf Kind-Routen. Navigiert selbststaendig per router.push und traegt die
 * aktuelle Query mit (Filter bleiben beim Tab-Wechsel erhalten).
 *
 * A11y: role="tablist", jeder Tab role="tab", aria-current="page" auf dem
 * aktiven Tab (Vorgabe der Spezifikation — bewusst kein aria-selected, das
 * waere das ueblichere ARIA-Tab-Muster, aber die Spec verlangt explizit
 * aria-current). Tastatur: ←/→ wechselt Tab, Home/End erster/letzter,
 * Enter/Space aktiviert (native <button>-Semantik).
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

export type SimTabKey = 'pipeline' | 'feed' | 'threads' | 'rounds' | 'actions'

const props = defineProps<{
  activeTab: SimTabKey
  simulationId: string
}>()

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const ROUTE_NAMES: Record<SimTabKey, string> = {
  pipeline: 'StepSimulation',
  feed: 'StepSimulationFeed',
  threads: 'SimThreads',
  rounds: 'SimRounds',
  actions: 'SimActions',
}

const TABS: Array<{ key: SimTabKey; labelKey: string }> = [
  { key: 'pipeline', labelKey: 'feed.pipeline' },
  { key: 'feed', labelKey: 'feed.feedTab' },
  { key: 'threads', labelKey: 'feed.threadsTab' },
  { key: 'rounds', labelKey: 'feed.roundsTab' },
  { key: 'actions', labelKey: 'feed.actionsTab' },
]

const tabRefs = ref<Array<HTMLButtonElement | null>>([])

function go(key: SimTabKey): void {
  if (key === props.activeTab) return
  void router.push({
    name: ROUTE_NAMES[key],
    params: { simulationId: props.simulationId },
    query: route.query,
  })
}

function onKeydown(event: KeyboardEvent, index: number): void {
  let nextIndex: number | null = null
  if (event.key === 'ArrowRight') nextIndex = (index + 1) % TABS.length
  else if (event.key === 'ArrowLeft') nextIndex = (index - 1 + TABS.length) % TABS.length
  else if (event.key === 'Home') nextIndex = 0
  else if (event.key === 'End') nextIndex = TABS.length - 1
  if (nextIndex === null) return
  event.preventDefault()
  go(TABS[nextIndex].key)
  tabRefs.value[nextIndex]?.focus()
}
</script>

<template>
  <div class="stb-root" role="tablist">
    <button
      v-for="(tab, idx) in TABS"
      :key="tab.key"
      :ref="(el) => (tabRefs[idx] = el as HTMLButtonElement | null)"
      type="button"
      role="tab"
      class="stb-tab"
      :class="{ 'stb-tab--active': tab.key === activeTab }"
      :aria-current="tab.key === activeTab ? 'page' : undefined"
      :tabindex="tab.key === activeTab ? 0 : -1"
      @click="go(tab.key)"
      @keydown="onKeydown($event, idx)"
    >
      {{ t(tab.labelKey) }}
    </button>
  </div>
</template>

<style scoped>
.stb-root {
  display: flex;
  gap: 24px;
  border-bottom: 1px solid var(--hairline);
}
.stb-tab {
  display: inline-flex;
  align-items: center;
  height: 36px;
  padding: 0 4px;
  font-size: 14px;
  font-weight: 500;
  font-family: var(--font-sans);
  color: var(--text-secondary);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  cursor: pointer;
  white-space: nowrap;
  transition: color 100ms ease, border-color 100ms ease;
  outline: none;
}
.stb-tab:hover:not(.stb-tab--active) {
  color: var(--text-primary);
}
.stb-tab--active {
  color: var(--text-primary);
  font-weight: 600;
  border-bottom-color: var(--accent);
}
.stb-tab:focus-visible {
  outline: var(--v4-state-focus-ring-width) solid var(--v4-state-focus-ring);
  outline-offset: var(--v4-state-focus-ring-offset);
  border-radius: var(--r-3);
}
</style>
