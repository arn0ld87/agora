<script setup lang="ts">
/**
 * SimRunHeader — kompakter Statusstreifen fuer Feed/Diskurs/Runden/Protokoll.
 *
 * Slice UI-2b (#1713), docs/design/simulation-feed.md §2.3. Ersetzt
 * SimulationPulseBar.vue (bleibt vorerst im Baum, wird aber nirgends mehr
 * importiert — Loeschung im letzten Commit der Serie).
 *
 * Zustaende: `loading` (Werte durch "—" ersetzt, aria-busy="true"),
 * `degraded` (Streifen behaelt Struktur, ein Chip zeigt den Text — nie als
 * Erfolg gefaerbt).
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

export type StreamState = 'connecting' | 'open' | 'reconnecting' | 'closed' | 'ended'

export interface SimRunHeaderDegradation {
  kind: 'snapshot_missing' | 'stream_lost' | 'legacy_run'
  hint: string
}

const props = withDefaults(
  defineProps<{
    simulationId: string
    currentRound: number | null
    totalRounds: number | null
    simTime: string | null
    postCount: number
    streamState: StreamState
    degradation?: SimRunHeaderDegradation | null
    loading?: boolean
  }>(),
  { degradation: null, loading: false },
)

const { t, te } = useI18n()

const roundLabel = computed(() => {
  if (props.loading) return '—'
  if (props.currentRound === null) return t('feed.header.roundUnknown')
  return t('feed.header.round', {
    current: props.currentRound,
    total: props.totalRounds ?? '—',
  })
})

const simTimeLabel = computed(() => {
  if (props.loading || !props.simTime) return '—'
  return props.simTime.slice(0, 16).replace('T', ' ')
})

const postCountLabel = computed(() =>
  props.loading ? '—' : t('feed.header.posts', { count: props.postCount }),
)

const streamLabelKey: Record<StreamState, string> = {
  connecting: 'feed.header.streamConnecting',
  open: 'feed.header.streamOpen',
  reconnecting: 'feed.header.streamReconnecting',
  closed: 'feed.header.streamClosed',
  ended: 'feed.header.streamEnded',
}

const streamLabel = computed(() => t(streamLabelKey[props.streamState]))

const degradationHint = computed(() => {
  const deg = props.degradation
  if (!deg) return null
  const key = `feed.degradation.${deg.kind}`
  return te(key) ? t(key) : deg.hint
})
</script>

<template>
  <div
    class="srh-root"
    role="group"
    :aria-busy="loading ? 'true' : 'false'"
    :aria-label="t('feed.live')"
  >
    <span class="srh-live-dot" :data-state="streamState" aria-hidden="true"></span>
    <span class="srh-stream" role="status">{{ streamLabel }}</span>
    <span class="srh-divider" aria-hidden="true">·</span>
    <span class="srh-round">{{ roundLabel }}</span>
    <span class="srh-divider" aria-hidden="true">·</span>
    <span class="srh-simtime">{{ simTimeLabel }}</span>
    <span class="srh-divider" aria-hidden="true">·</span>
    <span class="srh-count">{{ postCountLabel }}</span>
    <span v-if="degradationHint" class="srh-degradation" role="alert">{{ degradationHint }}</span>
  </div>
</template>

<style scoped>
.srh-root {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  padding: var(--sim-header-py) var(--sim-header-px);
  background: var(--surface-inset);
  border-bottom: 1px solid var(--hairline);
  font-size: var(--sim-time-fs);
  color: var(--text-secondary);
}
.srh-live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--sim-live-dot-closed);
}
.srh-live-dot[data-state='open'] {
  background: var(--sim-live-dot-open);
  animation: srh-pulse 1.5s ease-in-out infinite;
}
.srh-live-dot[data-state='connecting'],
.srh-live-dot[data-state='reconnecting'] {
  background: var(--sim-live-dot-reconnect);
  animation: srh-pulse 1.5s ease-in-out infinite;
}
@keyframes srh-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
@media (prefers-reduced-motion: reduce) {
  .srh-live-dot {
    animation: none;
  }
}
.srh-divider {
  color: var(--hairline);
}
.srh-degradation {
  margin-left: auto;
  padding: 2px 8px;
  border-radius: var(--r-2);
  background: var(--status-warning-soft, var(--status-orange-bg));
  color: var(--status-warning, var(--status-orange));
  font-weight: 600;
}
</style>
