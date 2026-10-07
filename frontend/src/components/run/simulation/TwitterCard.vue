<script setup lang="ts">
/**
 * Beitragskarte der Twitter-Zeitleiste (#1801): Byline, Text, eingebettetes
 * Zitat, Repost-Hinweis und Zähler mit zugänglichen Namen. Klick oder Enter auf
 * der Karte öffnet den Beitrag; die Zeitangabe ist zusätzlich ein echter Link.
 */
import { computed } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { TimelineEntry } from '@/composables/run/simulation/threads'
import PostByline from './PostByline.vue'

const props = defineProps<{
  entry: TimelineEntry
  to: RouteLocationRaw
  selected?: boolean
}>()
const emit = defineEmits<{ open: []; focus: [personaId: string] }>()
const { t } = useI18n()

const post = computed(() => props.entry.post)
const isRepost = computed(() => props.entry.kind === 'repost')
const quoteText = computed(() => props.entry.quotedPost?.body ?? post.value.quote_body ?? '')
</script>

<template>
  <article
    class="tcard"
    :class="{ 'tcard--selected': selected }"
    tabindex="0"
    data-testid="twitter-card"
    :data-post-id="post.post_id"
    @click="emit('open')"
    @keydown.enter.self="emit('open')"
    @focus="emit('focus', post.persona_id)"
  >
    <PostByline :post="post" />
    <p v-if="isRepost" class="tcard__repost" data-testid="twitter-card-repost">
      {{ t('views.run.simFeed.post.reposted') }}
    </p>
    <p v-if="post.body" class="tcard__body">{{ post.body }}</p>
    <blockquote v-if="entry.kind === 'quote' && quoteText" class="tcard__quote" data-testid="twitter-card-quote">
      <span class="tcard__quote-label">{{ t('views.run.simFeed.post.quoteOf') }}</span>
      {{ quoteText }}
    </blockquote>
    <p v-if="entry.referenceMissing" class="tcard__note" data-testid="twitter-card-reference-missing">
      {{ t('views.run.simFeed.post.referenceMissing') }}
    </p>
    <ul class="tcard__counts" :aria-label="t('views.run.simFeed.post.counts')" data-testid="twitter-card-counts">
      <li data-testid="count-replies">{{ t('views.run.simFeed.post.replies', entry.replies) }}</li>
      <li data-testid="count-reposts">{{ t('views.run.simFeed.post.reposts', entry.reposts) }}</li>
      <li data-testid="count-likes">{{ t('views.run.simFeed.post.likes', entry.likes) }}</li>
    </ul>
    <router-link :to="to" class="tcard__link" :aria-label="t('views.run.simFeed.post.open', { name: post.persona_name })" data-testid="twitter-card-link" @click.stop>
      {{ t('views.run.simFeed.post.openLink') }}
    </router-link>
  </article>
</template>

<style scoped>
.tcard {
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
.tcard:hover {
  background: var(--s3);
}
.tcard:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.tcard--selected {
  border-color: var(--acc);
}
.tcard__repost,
.tcard__note {
  margin: 0;
  font-size: 12px;
  color: var(--fg2);
}
.tcard__body {
  margin: 0;
  font-size: 14px;
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.tcard__quote {
  margin: 0;
  padding: 8px 10px;
  border-left: 3px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg2);
  font-size: 13px;
  overflow-wrap: anywhere;
}
.tcard__quote-label {
  display: block;
  color: var(--fg3);
  font-size: 12px;
  font-weight: 600;
}
.tcard__counts {
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
.tcard__link {
  align-self: flex-start;
  color: var(--acc);
  font-size: 12px;
  font-weight: 600;
}
.tcard__link:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
</style>
