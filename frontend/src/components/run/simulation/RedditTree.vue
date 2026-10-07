<script setup lang="ts">
/**
 * Eingerückter, einklappbarer Kommentarbaum eines Reddit-Beitrags (#1801).
 * Je Kommentar mit Antworten ein Knopf mit `aria-expanded` (Tastatur: Enter,
 * Leertaste). Rekursiv über den Dateinamen.
 */
import { reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import type { RedditNode } from '@/composables/run/simulation/threads'
import PostByline from './PostByline.vue'

defineProps<{
  nodes: readonly RedditNode[]
  claimId?: string | null
}>()
const { t } = useI18n()

const collapsed = reactive<Record<string, boolean>>({})

function descendants(node: RedditNode): number {
  return node.children.reduce((sum, child) => sum + 1 + descendants(child), 0)
}
function toggle(id: string): void {
  collapsed[id] = !collapsed[id]
}
function panelId(node: RedditNode): string {
  return `reddit-branch-${node.post.post_id.replace(/[^A-Za-z0-9_-]/g, '_')}`
}
</script>

<template>
  <ul class="rtree" data-testid="reddit-tree">
    <li
      v-for="node in nodes"
      :key="node.post.post_id"
      class="rtree__node"
      :data-depth="node.depth"
      data-testid="reddit-node"
    >
      <article
        class="rtree__item"
        :class="{ 'rtree__item--claim': claimId === node.post.post_id }"
        :aria-current="claimId === node.post.post_id ? 'true' : undefined"
      >
        <PostByline :post="node.post" />
        <p v-if="node.post.body" class="rtree__body">{{ node.post.body }}</p>
        <p v-if="node.parentMissing" class="rtree__meta" data-testid="reddit-parent-missing">
          {{ t('views.run.simFeed.tree.parentMissing') }}
        </p>
        <button
          v-if="node.children.length > 0"
          type="button"
          class="rtree__toggle"
          :aria-expanded="!collapsed[node.post.post_id]"
          :aria-controls="panelId(node)"
          data-testid="reddit-toggle"
          @click="toggle(node.post.post_id)"
        >
          {{
            collapsed[node.post.post_id]
              ? t('views.run.simFeed.tree.expand', { name: node.post.persona_name, count: descendants(node) })
              : t('views.run.simFeed.tree.collapse', { name: node.post.persona_name })
          }}
        </button>
      </article>
      <div v-if="node.children.length > 0" v-show="!collapsed[node.post.post_id]" :id="panelId(node)">
        <RedditTree :nodes="node.children" :claim-id="claimId" />
      </div>
    </li>
  </ul>
</template>

<style scoped>
.rtree {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.rtree__node > div {
  margin: 8px 0 0 12px;
  padding-left: 12px;
  border-left: 2px solid var(--line);
}
.rtree__item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s2);
  color: var(--fg);
}
.rtree__item--claim {
  border-color: var(--acc);
}
.rtree__body {
  margin: 0;
  font-size: 14px;
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.rtree__meta {
  margin: 0;
  color: var(--fg2);
  font-size: 12px;
}
.rtree__toggle {
  align-self: flex-start;
  padding: 2px 8px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg2);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.rtree__toggle:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
</style>
