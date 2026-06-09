<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import Badge from '../ui/Badge.vue'
import Kicker from '@/components/v4/data/Kicker.vue'
import FeedColumn from '../v4/sim-feed/FeedColumn.vue'
import TwitterPost from '../v4/sim-feed/TwitterPost.vue'
import RedditThread from '../v4/sim-feed/RedditThread.vue'
import type { PostCreatedEvent } from '@/contracts/postEventContract'
import type { RedditNode } from '@/composables/useSimFeed'

const { t } = useI18n()

defineProps<{
  allActionsCount: number
  twitterPosts: PostCreatedEvent[]
  redditPosts: PostCreatedEvent[]
  redditTree: RedditNode[]
  feedDensity?: string
  toolPanelOpen?: boolean
  toolPanelUnreadErrors?: number
}>()

const emit = defineEmits(['set-density', 'toggle-tool-panel'])
</script>

<template>
  <article class="card" data-testid="persona-action-feed">
    <header class="card-head">
      <Kicker num="03" accent>{{ t('step3.feed.title') }}</Kicker>
      <div class="log-meta">
        <Badge variant="ghost">{{ allActionsCount }} actions</Badge>
        <button
          type="button"
          class="tool-panel-toggle"
          :aria-expanded="toolPanelOpen"
          :title="toolPanelOpen ? t('step3.toolPanel.hide') : t('step3.toolPanel.show')"
          @click="emit('toggle-tool-panel')"
        >
          <span class="icon">{{ toolPanelOpen ? '▾' : '▸' }}</span>
          <span>{{ t('step3.toolPanel.toggle') }}</span>
          <span
            v-if="toolPanelUnreadErrors > 0 && !toolPanelOpen"
            class="tool-panel-badge"
            :aria-label="t('step3.toolPanel.unread', toolPanelUnreadErrors)"
          >{{ toolPanelUnreadErrors }}</span>
        </button>
      </div>
    </header>
    <div class="card-head feed-density-row">
      <div class="density-toggle" role="group" :aria-label="t('step3.feed.density.label')">
        <button
          type="button"
          class="density-btn"
          :class="{ active: feedDensity === 'comfort' }"
          :aria-pressed="feedDensity === 'comfort'"
          @click="emit('set-density', 'comfort')"
        >{{ t('step3.feed.density.comfort') }}</button>
        <button
          type="button"
          class="density-btn"
          :class="{ active: feedDensity === 'compact' }"
          :aria-pressed="feedDensity === 'compact'"
          @click="emit('set-density', 'compact')"
        >{{ t('step3.feed.density.compact') }}</button>
      </div>
      <span class="meta">{{ allActionsCount }}</span>
    </div>
    <div class="feed-grid" :data-density="feedDensity">
      <FeedColumn :title="t('feed.twitter')" channel="twitter">
        <TransitionGroup name="slide-in" tag="div" class="post-list">
          <TwitterPost
            v-for="post in twitterPosts"
            :key="post.post_id"
            :post="post"
          />
        </TransitionGroup>
        <p v-if="!twitterPosts.length" class="meta">{{ t('step3.feed.empty') }}</p>
      </FeedColumn>
      <FeedColumn :title="t('feed.reddit')" channel="reddit">
        <TransitionGroup name="slide-in" tag="div" class="post-list">
          <RedditThread
            v-for="node in redditTree"
            :key="node.post_id"
            :node="node"
          />
        </TransitionGroup>
        <p v-if="!redditPosts.length" class="meta">{{ t('step3.feed.empty') }}</p>
      </FeedColumn>
    </div>
  </article>
</template>

<style scoped>
.card {
  background: var(--bg);
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  padding: var(--s-5);
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}
.card-head {
  display: flex; justify-content: space-between; align-items: center;
  border-bottom: 1px solid var(--rule);
  padding-bottom: var(--s-3);
}
.log-meta { display: flex; gap: var(--s-2); }
.feed-density-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: none;
  padding-top: var(--s-2);
}
.feed-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--s-3);
  min-height: 0;
  overflow: visible;
}
.feed-grid > * { min-height: 480px; max-height: clamp(480px, 60vh, 720px); }
.feed-grid[data-density="comfort"] {
  --feed-post-padding: var(--s-3);
  --feed-post-gap: var(--s-2);
  --feed-post-fs: var(--fs-13, 13px);
  --feed-post-lh: 1.6;
}
.feed-grid[data-density="compact"] {
  --feed-post-padding: var(--s-2);
  --feed-post-gap: 4px;
  --feed-post-fs: 12px;
  --feed-post-lh: 1.35;
  gap: var(--s-2);
}
@media (max-width: 880px) {
  .feed-grid { grid-template-columns: 1fr; }
}
.density-toggle {
  display: inline-flex;
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  overflow: hidden;
}
.density-btn {
  background: transparent;
  border: 0;
  padding: 4px 10px;
  font-family: var(--font-sans, var(--ff-mono));
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  cursor: pointer;
  transition: background 120ms ease, color 120ms ease;
}
.density-btn + .density-btn { border-left: 1px solid var(--rule); }
.density-btn:hover { color: var(--fg); }
.density-btn.active { background: var(--accent); color: var(--bg); }
.tool-panel-toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  background: transparent;
  border: 1px solid var(--hairline, var(--rule));
  border-radius: var(--r-5, var(--r-1));
  padding: 4px 10px;
  font-family: var(--font-sans, var(--ff-sans));
  font-size: 11px;
  color: var(--fg-muted);
  cursor: pointer;
  transition: border-color 120ms ease, color 120ms ease;
  background: var(--surface-elevated, transparent);
  box-shadow: var(--shadow-control, none);
}
.tool-panel-toggle:hover {
  background: var(--surface-hover, transparent);
  color: var(--accent);
  border-color: var(--accent);
}
.tool-panel-toggle .icon { font-size: 13px; line-height: 1; }
.tool-panel-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  border-radius: 9px;
  background: var(--status-red, var(--status-error, #c53030));
  color: var(--text-on-accent, var(--bg));
  font-size: 10px;
  font-weight: 700;
}
.meta { color: var(--fg-muted); font-family: var(--ff-mono); font-size: 11px; letter-spacing: var(--ls-mono); }
</style>
