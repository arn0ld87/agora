<script setup lang="ts">
/**
 * StepSimulationFeedView — Dual-Column Sim-Feed (Reddit threaded + Twitter flat).
 *
 * Slice FE-Redesign-5 · 2026-05-15
 *
 * useEventStream-API: handlers werden im Constructor übergeben, nicht via .on().
 * post_created-Handler routet direkt in useSimFeed.ingest().
 */
import { onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { useEventStream } from '@/composables/useEventStream'
import { useSimFeed } from '@/composables/useSimFeed'
import { getSimulationFeedSnapshot } from '@/api/simulation'
import FeedColumn from '@/components/v4/sim-feed/FeedColumn.vue'
import RedditThread from '@/components/v4/sim-feed/RedditThread.vue'
import TwitterPost from '@/components/v4/sim-feed/TwitterPost.vue'
import SimulationPulseBar from '@/components/v4/sim-feed/SimulationPulseBar.vue'

const route = useRoute()
const simulationId = String(route.params.simulationId)
const feed = useSimFeed(simulationId)

// useEventStream nimmt handlers im Constructor — kein .on()-API.
// post_created ist bereits Zod-geparst durch openSimulationStream (Slice 5-pre).
const stream = useEventStream(simulationId, {
  post_created: (data) => feed.ingest(data),
})

onMounted(async () => {
  // #1009 — Snapshot beim Mount: den bisherigen Sim-Bestand aus der SQLite-DB
  // laden, bevor der SSE-Stream startet. So ist der Feed sofort befüllt und
  // dedup (useSimFeed.seen per post_id) verhindert, dass Live-Events die
  // bereits geladenen Posts doppelt einfügen. Fehler beim Fetch brechen den
  // Stream-Start nicht — der Live-Pfad bleibt allein nutzbar.
  try {
    const [reddit, twitter] = await Promise.all([
      getSimulationFeedSnapshot(simulationId, 'reddit').catch(() => []),
      getSimulationFeedSnapshot(simulationId, 'twitter').catch(() => []),
    ])
    feed.ingestMany([...reddit, ...twitter])
  } catch {
    // Beide Catches oben schlucken schon den Einzelfehler; dieser Block ist
    // nur die Defensive für den Fall, dass ingestMany selbst wirft.
  }
  await stream.start()
})

onBeforeUnmount(() => {
  // Gepufferte, aber noch nicht in all.value geschriebene Posts (rAF-Batch
  // in useSimFeed) vor dem Stream-Stop synchron uebernehmen, sonst gehen sie
  // beim Verlassen der Route verloren.
  feed.flushPending()
  stream.stop()
  // clearSimFeed(simulationId) bewusst NICHT mehr hier: eine normale
  // Navigation weg von der Feed-Route (und zurueck) hat bislang den
  // gesamten empfangenen Bestand vernichtet (#1007). "Stream schliessen"
  // und "Daten verwerfen" sind getrennt.
  //
  // Beim Wechsel der simulationId wird hier bewusst NICHTS geleert. `feed`
  // und `stream` sind an den Snapshot aus Z. 20 gebunden; die Component
  // wird laut Router-Konfiguration ohne :key wiederverwendet, ein Re-Init
  // faende also nicht statt. Wuerde man den Store der alten ID trotzdem
  // leeren, zeigte der View danach eine leere Liste UND bekaeme mangels
  // neuem Stream keine Daten mehr — schlechter als der Zustand vor diesem
  // Slice. Der Simulationswechsel bleibt damit unveraendert unbehandelt
  // (#1007 ist auf den Unmount-Datenverlust begrenzt); aufgeraeumt wird
  // ueber die MAX_STORES-LRU in useSimFeed.
})
</script>

<template>
  <div class="sf-root">
    <SimulationPulseBar
      :activity-rate="feed.activityRate.value"
      :reddit-count="feed.redditPosts.value.length"
      :twitter-count="feed.twitterPosts.value.length"
    />
    <div class="sf-columns">
      <FeedColumn
        :title="$t('feed.reddit')"
        channel="reddit"
        :has-items="feed.redditPosts.value.length > 0"
      >
        <TransitionGroup name="slide-in" tag="div" class="sf-thread-list">
          <RedditThread
            v-for="node in feed.redditTree.value"
            :key="node.post_id"
            :node="node"
          />
        </TransitionGroup>
        <p v-if="feed.redditPosts.value.length === 0" class="sf-empty">
          {{ $t('feed.empty') }}
        </p>
      </FeedColumn>

      <FeedColumn
        :title="$t('feed.twitter')"
        channel="twitter"
        :has-items="feed.twitterPosts.value.length > 0"
      >
        <TransitionGroup name="slide-in" tag="div" class="sf-post-list">
          <TwitterPost
            v-for="post in feed.twitterPosts.value"
            :key="post.post_id"
            :post="post"
          />
        </TransitionGroup>
        <p v-if="feed.twitterPosts.value.length === 0" class="sf-empty">
          {{ $t('feed.empty') }}
        </p>
      </FeedColumn>
    </div>
  </div>
</template>

<style scoped>
.sf-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.sf-columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  flex: 1;
  min-height: 0;
  padding: 16px;
}
.sf-thread-list,
.sf-post-list {
  display: flex;
  flex-direction: column;
}
.sf-empty {
  padding: 24px 12px;
  text-align: center;
  font-size: 13px;
  color: var(--text-secondary, #6b7280);
  margin: 0;
}

/* Slide-in Animation für neue Posts */
.slide-in-enter-active {
  transition: opacity 200ms ease, transform 200ms ease;
}
.slide-in-enter-from {
  opacity: 0;
  transform: translateY(-8px);
}
.slide-in-leave-active {
  display: none; /* Posts werden nicht entfernt */
}
@media (prefers-reduced-motion: reduce) {
  .slide-in-enter-active {
    transition: none;
  }
}

/* Responsive: untereinander auf schmalen Screens */
@media (max-width: 768px) {
  .sf-columns {
    grid-template-columns: 1fr;
    overflow-y: auto;
  }
}
</style>
