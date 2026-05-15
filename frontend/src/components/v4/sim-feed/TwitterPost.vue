<script setup lang="ts">
import type { PostCreatedEvent } from '@/contracts/postEventContract'
import PersonaAvatar from './PersonaAvatar.vue'
import SimBadge from './SimBadge.vue'

defineProps<{ post: PostCreatedEvent }>()
</script>

<template>
  <article class="tw-root" role="article">
    <PersonaAvatar :persona-id="post.persona_id" :voice-register="post.voice_register" />
    <div class="tw-body">
      <header class="tw-header">
        <span class="tw-handle">@{{ post.persona_id }}</span>
        <SimBadge v-if="post.is_simulated" />
        <time class="tw-time" :datetime="post.timestamp">{{ post.timestamp.slice(11, 16) }}</time>
      </header>
      <p class="tw-content">{{ post.body }}</p>
    </div>
  </article>
</template>

<style scoped>
.tw-root {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--hairline, #e5e7eb);
  transition: background 150ms;
}
.tw-root:hover {
  background: var(--surface-hover, #f9fafb);
}
.tw-body {
  flex: 1;
  min-width: 0;
}
.tw-header {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}
.tw-handle {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary, #111827);
}
.tw-time {
  font-size: 11px;
  color: var(--text-secondary, #6b7280);
  margin-left: auto;
}
.tw-content {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-primary, #111827);
}
</style>
