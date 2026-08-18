<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import RedditPost from './RedditPost.vue'
import type { RedditNode } from '@/composables/useSimFeed'

const props = defineProps<{ node: RedditNode; depth?: number }>()

const MAX_DEPTH = 4
const { t } = useI18n()
</script>

<template>
  <div class="rt-root" :style="{ paddingLeft: `${(props.depth ?? 0) * 16}px` }">
    <RedditPost :post="node" :depth="depth ?? 0" />
    <template v-if="(depth ?? 0) < MAX_DEPTH">
      <RedditThread
        v-for="child in node.children"
        :key="child.post_id"
        :node="child"
        :depth="(depth ?? 0) + 1"
      />
    </template>
    <button
      v-else-if="node.children.length > 0"
      type="button"
      class="rt-show-more"
      @click.prevent
    >
      {{ t('feed.showMoreReplies', { count: node.children.length }, node.children.length) }}
    </button>
  </div>
</template>

<style scoped>
.rt-root {
  position: relative;
}
.rt-show-more {
  margin-top: 4px;
  margin-left: 40px;
  font-size: 12px;
  color: var(--status-teal);
  background: none;
  border: none;
  padding: 2px 4px;
  cursor: pointer;
  text-decoration: underline;
}
.rt-show-more:hover {
  color: var(--status-teal);
}
</style>
