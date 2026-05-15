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
import { useSimFeed, clearSimFeed } from '@/composables/useSimFeed'
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
  await stream.start()
})

onBeforeUnmount(() => {
  stream.stop()
  clearSimFeed(simulationId)
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
      <FeedColumn :title="$t('feed.reddit')" channel="reddit">
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

      <FeedColumn :title="$t('feed.twitter')" channel="twitter">
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
