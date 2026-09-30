<script setup lang="ts">
/**
 * SimRoundsList — Runden-Ansicht.
 *
 * Slice UI-2b (#1713), docs/design/simulation-feed.md §2.9. Ersetzt die
 * Aktivitaetsleiste aus SimulationPulseBar.vue. Datenquelle:
 * GET /api/simulation/<id>/rounds (RoundSummary[]).
 *
 * Deviation von der Spezifikation: RoundSummary (backend/app/contracts/
 * sim_action_contract.py, Zod-Spiegel simActionContract.ts) traegt kein
 * Zeitfenster (sim_time_start/sim_time_end) — nur round_num, platform,
 * action_counts. Die Zeile zeigt darum keine Zeitspanne; das waere ein
 * erfundenes Feld, kein Vertragsfeld. `loading`/`error`-Props sind gegenueber
 * der abgekuerzten TS-Signatur in §2.9 ergaenzt, weil der Zustaende-Absatz
 * (loading/empty/error) sie voraussetzt — analog zu FeedTimelineProps.
 *
 * Der Endpunkt liefert einen Eintrag PRO Plattform UND Runde; diese
 * Komponente gruppiert sie zu einer Zeile pro round_num mit einer
 * Teilzusammenfassung je Plattform.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Platform } from '@/contracts/postEventContract'
import type { RoundSummary, SimActionType } from '@/contracts/simActionContract'
import type { StreamState } from './SimRunHeader.vue'

export interface SimRoundsListError {
  code: string
  message: string
}

const props = withDefaults(
  defineProps<{
    rounds: RoundSummary[]
    activeRound: number | null
    streamState: StreamState
    loading?: boolean
    error?: SimRoundsListError | null
  }>(),
  { loading: false, error: null },
)

const emit = defineEmits<{ select: [round: number]; retry: [] }>()

const { t } = useI18n()

// Kanonische Reihenfolge fuer lesbare Zeilen; unbekannte Aktionsarten
// (Alt-/Fremdlaeufe) haengen ans Ende statt zu verschwinden.
const ACTION_ORDER: SimActionType[] = [
  'CREATE_POST',
  'CREATE_COMMENT',
  'REPOST',
  'QUOTE_POST',
  'LIKE_POST',
  'LIKE_COMMENT',
  'DISLIKE_POST',
  'DISLIKE_COMMENT',
  'FOLLOW',
  'MUTE',
  'SEARCH_POSTS',
  'SEARCH_USER',
  'TREND',
  'REFRESH',
  'INTERVIEW',
  'DO_NOTHING',
  'OTHER',
]

interface RoundRow {
  roundNum: number
  byPlatform: Partial<Record<Platform, Record<string, number>>>
}

const rows = computed<RoundRow[]>(() => {
  const map = new Map<number, RoundRow>()
  for (const entry of props.rounds) {
    if (!map.has(entry.round_num)) {
      map.set(entry.round_num, { roundNum: entry.round_num, byPlatform: {} })
    }
    map.get(entry.round_num)!.byPlatform[entry.platform] = entry.action_counts
  }
  return [...map.values()].sort((a, b) => a.roundNum - b.roundNum)
})

function orderedCounts(counts: Record<string, number>): Array<{ key: string; count: number }> {
  const known = ACTION_ORDER.filter((k) => (counts[k] ?? 0) > 0).map((k) => ({ key: k, count: counts[k] }))
  const unknown = Object.entries(counts)
    .filter(([k, v]) => v > 0 && !ACTION_ORDER.includes(k as SimActionType))
    .map(([key, count]) => ({ key, count }))
  return [...known, ...unknown]
}

// Nur bekannte SimActionType-Werte haben einen i18n-Eintrag (beide
// Locales, vollstaendig gepflegt). `action_counts` ist serverseitig ein
// offenes Record<string, number> — ein Fremdwert (Datendrift) zeigt den
// technischen Rohwert statt eines unaufgeloesten i18n-Schluessels.
function actionLabel(key: string): string {
  return ACTION_ORDER.includes(key as SimActionType) ? t(`feed.actionType.${key}`) : key
}

function hasAnyActions(row: RoundRow): boolean {
  return Object.values(row.byPlatform).some(
    (counts) => counts !== undefined && Object.values(counts).some((v) => v > 0),
  )
}

function select(roundNum: number): void {
  emit('select', roundNum)
}

function onKeydown(event: KeyboardEvent, roundNum: number): void {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    select(roundNum)
  }
}
</script>

<template>
  <div class="srl-root">
    <div v-if="loading" class="srl-skeleton" aria-busy="true">
      <div v-for="i in 5" :key="i" class="srl-skeleton-row"></div>
    </div>

    <div v-else-if="error" class="srl-banner" role="alert">
      <span>{{ t('feed.rounds.error') }}</span>
      <button type="button" class="srl-retry" @click="emit('retry')">
        {{ t('feed.rounds.retry') }}
      </button>
    </div>

    <p v-else-if="rows.length === 0" class="srl-empty" role="status">
      {{ t('feed.rounds.empty') }}
    </p>

    <ul v-else class="srl-list" role="list">
      <li v-for="row in rows" :key="row.roundNum" class="srl-item">
        <div
          class="srl-row"
          role="button"
          tabindex="0"
          :aria-current="row.roundNum === activeRound ? 'true' : undefined"
          :class="{ 'srl-row--active': row.roundNum === activeRound }"
          @click="select(row.roundNum)"
          @keydown="(event) => onKeydown(event, row.roundNum)"
        >
          <span class="srl-round-chip">{{ t('feed.roundsList.roundLabel', { round: row.roundNum }) }}</span>
          <div class="srl-platforms">
            <div v-for="platform in (['reddit', 'twitter'] as const)" :key="platform">
              <div v-if="row.byPlatform[platform]" class="srl-platform-block">
                <span class="srl-platform-marker" :data-platform="platform" aria-hidden="true">
                  {{ platform === 'reddit' ? 'R' : 'T' }}
                </span>
                <span
                  v-for="entry in orderedCounts(row.byPlatform[platform]!)"
                  :key="entry.key"
                  class="srl-count"
                >
                  {{ actionLabel(entry.key) }}: {{ entry.count }}
                </span>
              </div>
            </div>
          </div>
          <p v-if="!hasAnyActions(row)" class="srl-no-actions">{{ t('feed.roundsList.noActions') }}</p>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.srl-root {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.srl-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.srl-item + .srl-item {
  border-top: var(--sim-item-divider);
}
.srl-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: var(--sim-item-py) var(--sim-item-px);
  cursor: pointer;
}
.srl-row:hover {
  background: var(--surface-hover);
}
.srl-row:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
.srl-row--active {
  background: var(--sim-item-new-bg);
}
.srl-round-chip {
  font-weight: 600;
  font-size: var(--sim-persona-fs);
  color: var(--text-primary);
}
.srl-platforms {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.srl-platform-block {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.srl-platform-marker {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: var(--r-2);
  background: var(--sim-badge-bg);
  color: var(--text-primary);
  font-size: 9px;
  font-weight: 700;
  flex-shrink: 0;
}
.srl-count {
  font-size: 11.5px;
  color: var(--text-secondary);
}
.srl-no-actions {
  margin: 0;
  font-size: 11.5px;
  color: var(--text-tertiary);
  font-style: italic;
}
.srl-empty {
  margin: 0;
  padding: 32px 16px;
  text-align: center;
  font-size: 13px;
  color: var(--text-secondary);
}
.srl-banner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: var(--sim-header-py) var(--sim-header-px);
  font-size: var(--sim-time-fs);
  background: var(--status-danger-soft, var(--status-red-bg, rgba(224, 122, 104, 0.14)));
  color: var(--status-red);
}
.srl-retry {
  border: 1px solid currentColor;
  border-radius: var(--r-5);
  background: transparent;
  color: inherit;
  padding: 2px 10px;
  font-size: 12px;
  cursor: pointer;
}
.srl-skeleton {
  padding: var(--sim-item-py) var(--sim-item-px);
  display: flex;
  flex-direction: column;
  gap: var(--sim-item-gap);
}
.srl-skeleton-row {
  height: 48px;
  border-radius: var(--r-5);
  background: var(--surface-inset);
  animation: srl-shimmer 1.4s ease-in-out infinite;
}
@keyframes srl-shimmer {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 0.9; }
}
@media (prefers-reduced-motion: reduce) {
  .srl-skeleton-row {
    animation: none;
  }
}
</style>
