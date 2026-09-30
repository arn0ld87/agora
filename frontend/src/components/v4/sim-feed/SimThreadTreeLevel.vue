<script setup lang="ts">
/**
 * SimThreadTreeLevel — eine Rekursionsebene von SimThreadTree.vue (§2.8).
 *
 * Eigene Datei statt Inline-Rekursion, weil <script setup> sich nicht
 * selbst referenzieren kann, ohne den Datei-Namen als Tag zu importieren —
 * analog zum bestehenden Split RedditThread.vue/RedditPost.vue.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PostCreatedEvent } from '@/contracts/postEventContract'
import FeedItem from './FeedItem.vue'

const props = defineProps<{
  node: PostCreatedEvent
  threadRootId: string
  childrenMap: Map<string, PostCreatedEvent[]>
  depth: number
  maxDepth: number
}>()

const emit = defineEmits<{ openThread: [postId: string] }>()

const { t } = useI18n()

const children = computed(() => props.childrenMap.get(props.node.post_id) ?? [])
const showChildren = computed(() => props.depth < props.maxDepth)

function openThread(postId: string): void {
  emit('openThread', postId)
}

// §2.8: jenseits von maxDepth wird nicht mehr rekursiv aufgebaut — der Klick
// springt stattdessen in den Strang-Fokus des Unterbaums (dieser Knoten wird
// die neue Wurzel in SimThreadFocusView), statt lokal aufzuklappen. Das
// nutzt dieselbe openThread-Route wie ein Klick auf den Beitrag selbst und
// braucht keinen zusaetzlichen Expand-Zustand.
function showMore(): void {
  openThread(props.node.post_id)
}
</script>

<template>
  <div class="stl-root" :style="{ '--stl-depth': depth }">
    <FeedItem :post="node" :thread-root-id="threadRootId" @open-thread="openThread" />
    <template v-if="showChildren">
      <SimThreadTreeLevel
        v-for="child in children"
        :key="child.post_id"
          :node="child"
          :thread-root-id="threadRootId"
        :children-map="childrenMap"
        :depth="depth + 1"
        :max-depth="maxDepth"
        @open-thread="openThread"
      />
    </template>
    <button v-else-if="children.length > 0" type="button" class="stl-show-more" @click="showMore">
      {{ t('feed.showMoreReplies', { count: children.length }, children.length) }}
    </button>
  </div>
</template>

<style scoped>
.stl-root {
  position: relative;
  padding-left: calc(var(--sim-thread-indent) * var(--stl-depth, 1));
  border-left: var(--sim-thread-rule);
}
.stl-show-more {
  margin: 2px 0 6px 8px;
  font-size: 12px;
  color: var(--status-teal);
  background: none;
  border: none;
  padding: 2px 4px;
  cursor: pointer;
  text-decoration: underline;
}
</style>
