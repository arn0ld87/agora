<script setup lang="ts">
import type { PostCreatedEvent } from '@/contracts/postEventContract'
import PersonaAvatar from './PersonaAvatar.vue'
import SimBadge from './SimBadge.vue'

defineProps<{ post: PostCreatedEvent; depth: number }>()
</script>

<template>
  <article class="rp-root" role="article" :data-depth="depth">
    <div class="rp-rail" aria-hidden="true"></div>
    <PersonaAvatar :persona-id="post.persona_id" :voice-register="post.voice_register" />
    <div class="rp-body">
      <header class="rp-header">
        <span class="rp-user">u/{{ post.persona_id }}</span>
        <SimBadge v-if="post.is_simulated" />
        <time class="rp-time" :datetime="post.timestamp">{{ post.timestamp.slice(11, 16) }}</time>
      </header>
      <p class="rp-content">{{ post.body }}</p>
    </div>
  </article>
</template>

<style scoped>
.rp-root {
  display: flex;
  gap: 8px;
  padding: 8px 0;
  position: relative;
}
.rp-rail {
  position: absolute;
  left: -12px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--hairline, #e5e7eb);
  border-radius: 1px;
}
.rp-root[data-depth='0'] .rp-rail {
  display: none;
}
.rp-body {
  flex: 1;
  min-width: 0;
}
.rp-header {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 3px;
  flex-wrap: wrap;
}
.rp-user {
  font-weight: 600;
  font-size: 12px;
  color: var(--accent-blue, #2563eb);
}
.rp-time {
  font-size: 11px;
  color: var(--text-secondary, #6b7280);
  margin-left: auto;
}
.rp-content {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-primary, #111827);
}
</style>
