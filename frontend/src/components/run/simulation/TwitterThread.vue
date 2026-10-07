<script setup lang="ts">
/**
 * Faden-Ansicht eines Twitter-Beitrags (#1801): Beitrag oben, darunter die
 * Antworten mit Verbindungslinie (aus `depth` und `isLastChild`), Zitate und
 * Reposts. Fehlende Wurzel und fehlerhafte Kette stehen als Hinweis da, nie still.
 */
import type { RouteLocationRaw } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { ThreadResult } from '@/composables/run/simulation/threads'
import PostByline from './PostByline.vue'

defineProps<{
  result: ThreadResult
  /** Hebt den Beitrag mit dieser `post_id` hervor (`?claim=`). */
  claimId?: string | null
  toFor: (postId: string) => RouteLocationRaw
}>()
const { t } = useI18n()
</script>

<template>
  <div class="thread" data-testid="twitter-thread">
    <p v-if="result.broken" class="thread__notice thread__notice--err" role="alert" data-testid="thread-broken">
      {{ t('views.run.simFeed.thread.broken') }}
    </p>
    <p v-else-if="result.rootMissing" class="thread__notice" role="status" data-testid="thread-root-missing">
      {{ t('views.run.simFeed.thread.rootMissing') }}
    </p>

    <article
      v-if="result.root"
      class="thread__root"
      :class="{ 'thread__item--claim': claimId === result.root.post_id }"
      :aria-current="claimId === result.root.post_id ? 'true' : undefined"
      data-testid="thread-root"
    >
      <PostByline :post="result.root" />
      <p v-if="result.root.body" class="thread__body">{{ result.root.body }}</p>
      <p v-if="claimId === result.root.post_id" class="thread__claim" data-testid="thread-claim">
        {{ t('views.run.simFeed.thread.claim') }}
      </p>
      <p class="thread__meta" data-testid="thread-reposts">
        {{ t('views.run.simFeed.thread.reposts', { count: result.reposts }) }}
      </p>
    </article>

    <section v-if="!result.broken" :aria-label="t('views.run.simFeed.thread.replies')">
      <h3 class="thread__heading">{{ t('views.run.simFeed.thread.replies') }}</h3>
      <p v-if="result.nodes.length === 0" class="thread__empty" data-testid="thread-no-replies">
        {{ t('views.run.simFeed.thread.noReplies') }}
      </p>
      <ol v-else class="thread__list">
        <li
          v-for="node in result.nodes"
          :key="node.post.post_id"
          class="thread__node"
          :class="{ 'thread__node--last': node.isLastChild }"
          :style="{ '--depth': node.depth }"
          :data-depth="node.depth"
          :data-last="node.isLastChild ? 'true' : 'false'"
          data-testid="thread-node"
        >
          <article
            class="thread__item"
            :class="{ 'thread__item--claim': claimId === node.post.post_id }"
            :aria-current="claimId === node.post.post_id ? 'true' : undefined"
          >
            <PostByline :post="node.post" />
            <p v-if="node.post.body" class="thread__body">{{ node.post.body }}</p>
            <p v-if="node.parentMissing" class="thread__meta" data-testid="thread-parent-missing">
              {{ t('views.run.simFeed.thread.parentMissing') }}
            </p>
            <p v-if="claimId === node.post.post_id" class="thread__claim">
              {{ t('views.run.simFeed.thread.claim') }}
            </p>
          </article>
        </li>
      </ol>
    </section>

    <section v-if="result.quotes.length > 0" :aria-label="t('views.run.simFeed.thread.quotes')">
      <h3 class="thread__heading">{{ t('views.run.simFeed.thread.quotes') }}</h3>
      <ul class="thread__quotes" data-testid="thread-quotes">
        <li v-for="quote in result.quotes" :key="quote.post_id" class="thread__item">
          <PostByline :post="quote" />
          <p v-if="quote.body" class="thread__body">{{ quote.body }}</p>
          <router-link :to="toFor(quote.post_id)" class="thread__link">
            {{ t('views.run.simFeed.post.open', { name: quote.persona_name }) }}
          </router-link>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.thread {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.thread__notice {
  margin: 0;
  padding: 8px 12px;
  border-radius: var(--ag-r-8);
  background: var(--warn-soft);
  color: var(--warn);
  font-size: 13px;
  font-weight: 600;
}
.thread__notice--err {
  background: var(--err-soft);
  color: var(--err);
}
.thread__root,
.thread__item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg);
}
.thread__item--claim {
  border-color: var(--acc);
  background: var(--acc-soft, var(--s3));
}
.thread__body {
  margin: 0;
  font-size: 14px;
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.thread__meta,
.thread__empty {
  margin: 0;
  color: var(--fg2);
  font-size: 12px;
}
.thread__claim {
  margin: 0;
  color: var(--acc);
  font-size: 12px;
  font-weight: 650;
}
.thread__heading {
  margin: 0 0 8px;
  color: var(--fg3);
  font-size: 12px;
  font-weight: 600;
}
.thread__list,
.thread__quotes {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.thread__node {
  position: relative;
  margin-left: calc((var(--depth) - 1) * 24px);
  padding-left: 20px;
}
/* Verbindungslinie: senkrecht an der linken Kante, bei der letzten Antwort
   nur bis zum Ast. */
.thread__node::before {
  content: '';
  position: absolute;
  left: 6px;
  top: -8px;
  bottom: 0;
  border-left: 2px solid var(--line);
}
.thread__node--last::before {
  bottom: auto;
  height: 28px;
}
.thread__node::after {
  content: '';
  position: absolute;
  left: 6px;
  top: 20px;
  width: 12px;
  border-top: 2px solid var(--line);
}
.thread__link {
  align-self: flex-start;
  color: var(--acc);
  font-size: 12px;
  font-weight: 600;
}
.thread__link:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
</style>
