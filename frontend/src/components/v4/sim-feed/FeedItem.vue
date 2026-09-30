<script setup lang="ts">
/**
 * FeedItem — Rahmen fuer einen einzelnen Feed-Beitrag.
 *
 * Slice UI-2b (#1713), docs/design/simulation-feed.md §2.4. Ersetzt die
 * bisherige Direktdarstellung TwitterPost/RedditPost an den Feed-Wurzeln.
 * Beide Basiskomponenten bleiben Bausteine fuer den Beitragskoerper;
 * FeedItem ergaenzt Plattform-Markierung, Kontext-Zeile je `post.kind`,
 * Trennlinie unten (keine Karte) und die isNew-Markierung (§4).
 *
 * A11y: role="article", tabindex="0", Enter/Space oeffnet SimThreadFocus.
 * Kontext-Zeile ist per aria-describedby an den Artikel gebunden.
 */
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PostCreatedEvent } from '@/contracts/postEventContract'
import { useSimFeed } from '@/composables/useSimFeed'
import TwitterPost from './TwitterPost.vue'
import RedditPost from './RedditPost.vue'

const props = withDefaults(
  defineProps<{
    post: PostCreatedEvent
    isNew?: boolean
    showContext?: boolean
  }>(),
  { isNew: false, showContext: true },
)

const emit = defineEmits<{ openThread: [postId: string] }>()

const { t } = useI18n()

// Repost-Quelle wird ueber den Store derselben Simulation aufgeloest.
const feed = useSimFeed(props.post.simulation_id)

const platformLabel = computed(() => (props.post.platform === 'reddit' ? 'R' : 'T'))

// SimThreadFocus adressiert immer die Strang-Wurzel, nicht den Kommentar.
const threadPostId = computed(() => feed.resolveRootId(props.post))

function open(): void {
  if (threadPostId.value) emit('openThread', threadPostId.value)
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    open()
  }
}

const contextText = computed<string | null>(() => {
  if (!props.showContext) return null
  if (props.post.kind === 'comment') {
    return props.post.parent_persona_name
      ? t('feed.replyTo', { name: props.post.parent_persona_name })
      : t('feed.replyToUnknown')
  }
  if (props.post.kind === 'repost') {
    return t('feed.repostedBy', { name: props.post.persona_name })
  }
  return null
})

const quoteBody = computed<string | null>(() => {
  if (props.post.kind !== 'quote') return null
  return props.post.quote_body && props.post.quote_body.length > 0 ? props.post.quote_body : null
})

const repostedSource = computed<PostCreatedEvent | null>(() => {
  if (props.post.kind !== 'repost') return null
  const id = props.post.reposted_post_id
  if (!id) return null
  return feed.byId(id) ?? null
})

// isNew-Marker: 1500ms Highlight, dann faellt er ab (§4). Kein Autoscroll.
const showNewHighlight = ref(props.isNew)
let timer: ReturnType<typeof setTimeout> | null = null

onMounted(() => {
  if (props.isNew) {
    timer = setTimeout(() => {
      showNewHighlight.value = false
    }, 1500)
  }
})
onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})
</script>

<template>
  <div
    class="fi-root"
    :class="{ 'fi-root--new': showNewHighlight }"
    tabindex="0"
    role="article"
    :aria-describedby="contextText ? `fi-ctx-${post.post_id}` : undefined"
    @click="open"
    @keydown="onKeydown"
  >
    <span v-if="isNew" class="fi-new-dot" aria-hidden="true"></span>
    <span class="fi-platform" :data-platform="post.platform" aria-hidden="true">{{
      platformLabel
    }}</span>
    <div class="fi-content">
      <p v-if="contextText" :id="`fi-ctx-${post.post_id}`" class="fi-context">
        {{ contextText }}
      </p>

      <div v-if="post.kind === 'quote'" class="fi-quote">
        <p v-if="quoteBody" class="fi-quote-body">{{ quoteBody }}</p>
        <p v-else class="fi-quote-missing">{{ t('feed.quoteMissing') }}</p>
      </div>

      <RedditPost v-if="post.platform === 'reddit'" :post="post" :depth="0" />
      <TwitterPost v-else :post="post" />

      <template v-if="post.kind === 'repost'">
        <div v-if="repostedSource" class="fi-repost-body">
          <RedditPost v-if="repostedSource.platform === 'reddit'" :post="repostedSource" :depth="0" />
          <TwitterPost v-else :post="repostedSource" />
        </div>
        <p v-else class="fi-repost-missing">{{ t('feed.repostSourceMissing') }}</p>
      </template>
    </div>
  </div>
</template>

<style scoped>
.fi-root {
  position: relative;
  display: flex;
  gap: var(--sim-item-gap);
  padding: var(--sim-item-py) var(--sim-item-px);
  border-bottom: var(--sim-item-divider);
  transition: background-color 1500ms ease;
  cursor: pointer;
}
.fi-root:hover {
  background: var(--surface-hover);
}
.fi-root:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
.fi-root--new {
  background: var(--sim-item-new-bg);
}
.fi-new-dot {
  position: absolute;
  left: 4px;
  top: 50%;
  transform: translateY(-50%);
  width: 2px;
  height: 60%;
  border-radius: var(--r-2);
  background: var(--sim-new-dot);
}
.fi-platform {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  margin-top: 2px;
  border-radius: var(--r-2);
  background: var(--sim-badge-bg);
  font-size: 10px;
  font-weight: 700;
}
.fi-platform[data-platform='reddit'] {
  color: var(--sim-badge-fg-reddit);
}
.fi-platform[data-platform='twitter'] {
  color: var(--sim-badge-fg-twitter);
}
.fi-content {
  flex: 1;
  min-width: 0;
}
.fi-context {
  margin: 0 0 4px;
  font-size: var(--sim-time-fs);
  color: var(--text-secondary);
}
.fi-quote {
  margin-bottom: 6px;
  padding: 6px 10px;
  border-left: var(--sim-thread-rule);
  background: var(--surface-inset);
  border-radius: var(--r-2);
}
.fi-quote-body {
  margin: 0;
  font-size: var(--sim-time-fs);
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}
.fi-quote-missing,
.fi-repost-missing {
  margin: 4px 0 0;
  font-size: var(--sim-time-fs);
  color: var(--text-tertiary);
  font-style: italic;
}
.fi-repost-body {
  margin-top: 6px;
  padding-left: 10px;
  border-left: var(--sim-thread-rule);
}
</style>
