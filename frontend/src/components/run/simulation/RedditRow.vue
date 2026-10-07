<script setup lang="ts">
/**
 * Zeile der Reddit-Beitragsliste (#1801): Byline, Text, Stimmenstand und
 * Kommentarzahl. Klick oder Enter öffnet den Beitrag.
 */
import type { RouteLocationRaw } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { RedditListEntry } from '@/composables/run/simulation/threads'
import PostByline from './PostByline.vue'

defineProps<{ entry: RedditListEntry; to: RouteLocationRaw; selected?: boolean }>()
const emit = defineEmits<{ open: []; focus: [personaId: string] }>()
const { t } = useI18n()
</script>

<template>
  <article
    class="rrow"
    :class="{ 'rrow--selected': selected }"
    tabindex="0"
    data-testid="reddit-row"
    :data-post-id="entry.post.post_id"
    @click="emit('open')"
    @keydown.enter.self="emit('open')"
    @focus="emit('focus', entry.post.persona_id)"
  >
    <PostByline :post="entry.post" />
    <p v-if="entry.post.body" class="rrow__body">{{ entry.post.body }}</p>
    <ul class="rrow__counts" :aria-label="t('views.run.simFeed.post.counts')" data-testid="reddit-row-counts">
      <li data-testid="count-votes">{{ t('views.run.simFeed.post.votes', { n: entry.score }) }}</li>
      <li data-testid="count-comments">{{ t('views.run.simFeed.post.comments', entry.commentCount) }}</li>
    </ul>
    <router-link :to="to" class="rrow__link" :aria-label="t('views.run.simFeed.post.open', { name: entry.post.persona_name })" data-testid="reddit-row-link" @click.stop>
      {{ t('views.run.simFeed.post.openLink') }}
    </router-link>
  </article>
</template>

<style scoped>
.rrow {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg);
  cursor: pointer;
}
.rrow:hover {
  background: var(--s3);
}
.rrow:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.rrow--selected {
  border-color: var(--acc);
}
.rrow__body {
  margin: 0;
  font-size: 14px;
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.rrow__counts {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  margin: 0;
  padding: 0;
  list-style: none;
  color: var(--fg2);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.rrow__link {
  align-self: flex-start;
  color: var(--acc);
  font-size: 12px;
  font-weight: 600;
}
.rrow__link:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
</style>
