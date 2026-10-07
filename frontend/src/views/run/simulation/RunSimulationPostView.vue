<script setup lang="ts">
/**
 * Beitrag der Simulation (Etappe 4, #1801, Bauplan 4.5). Twitter: Faden mit
 * Antworten und Verbindungslinie. Reddit: Beitrag mit einklappbarem
 * Kommentarbaum. Das Netzwerk ergibt sich aus dem Präfix der `postId`
 * (`twitter:123`, `reddit:comment:7`); sie kann Doppelpunkte enthalten und wird
 * unverändert gereicht. `?claim=` bleibt erhalten und hebt den Beitrag hervor
 * (die Belegspalte folgt in Etappe 5). Kein `h1`: die Überschrift gehört dem
 * Arbeitsbereich.
 */
import { computed, toRef } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import FeedNotices from '@/components/run/simulation/FeedNotices.vue'
import PostByline from '@/components/run/simulation/PostByline.vue'
import RedditTree from '@/components/run/simulation/RedditTree.vue'
import TwitterThread from '@/components/run/simulation/TwitterThread.vue'
import { FEED_SNAPSHOT_LIMIT, useRunFeed } from '@/composables/run/simulation/useRunFeed'
import { buildRedditTree, buildTwitterThread } from '@/composables/run/simulation/threads'

const props = defineProps<{ simulationId: string; postId: string }>()
const { t } = useI18n()
const route = useRoute()

const feed = useRunFeed(toRef(props, 'simulationId'))

const network = computed(() => (props.postId.startsWith('reddit:') ? 'reddit' : 'twitter'))
const claimId = computed(() => {
  const raw = route.query.claim
  const value = Array.isArray(raw) ? raw[0] : raw
  return typeof value === 'string' && value !== '' ? value : null
})

const thread = computed(() =>
  network.value === 'twitter' ? buildTwitterThread(props.postId, feed.posts.value) : null,
)
const tree = computed(() =>
  network.value === 'reddit' ? buildRedditTree(props.postId, feed.posts.value) : null,
)

const backTo = computed(() => ({
  name: 'RunSimulationFeed',
  params: { simulationId: props.simulationId, network: network.value },
  query: route.query,
}))
function postTo(postId: string) {
  return {
    name: 'RunSimulationPost',
    params: { simulationId: props.simulationId, postId },
    query: route.query,
  }
}

const loading = computed(() => feed.loading.value && feed.posts.value.length === 0)
const streamError = computed(() => feed.streamState.value === 'error')
</script>

<template>
  <div class="post" data-testid="run-sim-post">
    <router-link :to="backTo" class="post__back" data-testid="post-back">
      {{ t('views.run.simFeed.thread.back') }}
    </router-link>

    <FeedNotices
      :error="feed.error.value"
      :truncated="feed.truncated.value"
      :limit="FEED_SNAPSHOT_LIMIT"
      :invalid-count="feed.invalidCount.value"
      :evicted-count="feed.evictedCount.value"
      :unrounded-count="0"
      :stream-error="streamError"
      @reload="feed.reload"
    />

    <p v-if="loading" class="post__state" role="status" data-testid="post-loading">
      {{ t('views.run.simFeed.thread.loading') }}
    </p>

    <TwitterThread
      v-else-if="thread"
      :result="thread"
      :claim-id="claimId"
      :to-for="postTo"
    />

    <section v-else-if="tree" class="post__tree" :aria-label="t('views.run.simFeed.tree.region')" data-testid="reddit-post">
      <p v-if="tree.rootMissing" class="post__notice" role="status" data-testid="tree-root-missing">
        {{ t('views.run.simFeed.thread.rootMissing') }}
      </p>
      <article
        v-else-if="tree.root"
        class="post__root"
        :class="{ 'post__root--claim': claimId === tree.root.post_id }"
        :aria-current="claimId === tree.root.post_id ? 'true' : undefined"
        data-testid="reddit-root"
      >
        <PostByline :post="tree.root" />
        <p v-if="tree.root.body" class="post__body">{{ tree.root.body }}</p>
        <p v-if="claimId === tree.root.post_id" class="post__claim">{{ t('views.run.simFeed.thread.claim') }}</p>
      </article>

      <p v-if="tree.flatOnly" class="post__notice" role="status" data-testid="tree-flat-only">
        {{ t('views.run.simFeed.tree.flatOnly') }}
      </p>
      <p v-if="tree.unplacedCount > 0" class="post__notice" role="status" data-testid="tree-unplaced">
        {{ t('views.run.simFeed.tree.unplaced', { count: tree.unplacedCount }) }}
      </p>
      <p v-if="tree.tree.length === 0" class="post__state" data-testid="tree-empty">
        {{ t('views.run.simFeed.tree.noComments') }}
      </p>
      <RedditTree v-else :nodes="tree.tree" :claim-id="claimId" />
    </section>
  </div>
</template>

<style scoped>
.post {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.post__back {
  align-self: flex-start;
  color: var(--acc);
  font-size: 13px;
  font-weight: 600;
}
.post__back:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.post__tree {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.post__root {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg);
}
.post__root--claim {
  border-color: var(--acc);
}
.post__body {
  margin: 0;
  font-size: 14px;
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.post__claim {
  margin: 0;
  color: var(--acc);
  font-size: 12px;
  font-weight: 650;
}
.post__notice {
  margin: 0;
  padding: 8px 12px;
  border-radius: var(--ag-r-8);
  background: var(--warn-soft);
  color: var(--warn);
  font-size: 13px;
  font-weight: 600;
}
.post__state {
  margin: 0;
  padding: 16px;
  border: 1px dashed var(--line);
  border-radius: var(--ag-r-12);
  color: var(--fg2);
  font-size: 13px;
}
</style>
