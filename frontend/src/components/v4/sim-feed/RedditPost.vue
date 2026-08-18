<script setup lang="ts">
import { computed } from 'vue'
import type { PostCreatedEvent } from '@/contracts/postEventContract'
import PersonaAvatar from './PersonaAvatar.vue'
import SimBadge from './SimBadge.vue'

const props = defineProps<{ post: PostCreatedEvent; depth: number }>()

const scoreClass = computed(() => {
  const s = props.post.score ?? 0
  if (s > 0) return 'rp-score--positive'
  if (s < 0) return 'rp-score--negative'
  return ''
})

const scoreDisplay = computed(() => {
  const s = props.post.score ?? 0
  if (s >= 1000) return `${(s / 1000).toFixed(1)}k`
  if (s <= -1000) return `-${(Math.abs(s) / 1000).toFixed(1)}k`
  return String(s)
})
</script>

<template>
  <article class="rp-root" role="article" :data-depth="depth">
    <div class="rp-rail" aria-hidden="true"></div>
    <!-- Voting-Bar (read-only, Reddit-typisch) -->
    <div class="rp-voting" aria-label="Voting-Score" role="img">
      <svg
        class="rp-arrow"
        aria-hidden="true"
        width="12"
        height="12"
        viewBox="0 0 12 12"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path d="M6 2L11 8H1L6 2Z" fill="currentColor" />
      </svg>
      <span class="rp-score" :class="scoreClass">{{ scoreDisplay }}</span>
      <svg
        class="rp-arrow"
        aria-hidden="true"
        width="12"
        height="12"
        viewBox="0 0 12 12"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path d="M6 10L1 4H11L6 10Z" fill="currentColor" />
      </svg>
    </div>
    <PersonaAvatar
      :persona-id="post.persona_id"
      :persona-name="post.persona_name"
      :voice-register="post.voice_register"
    />
    <div class="rp-body">
      <header class="rp-header">
        <span class="rp-user">u/{{ post.persona_name }}</span>
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
  background: var(--hairline);
  border-radius: 1px;
}
.rp-root[data-depth='0'] .rp-rail {
  display: none;
}
/* Voting-Bar */
.rp-voting {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-width: 36px;
  color: var(--text-tertiary);
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}
.rp-arrow {
  color: var(--text-tertiary);
  opacity: 0.6;
}
.rp-score {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  line-height: 1;
}
.rp-score--positive {
  color: var(--status-orange, #f97316);
}
.rp-score--negative {
  color: var(--status-teal);
}
/* Body */
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
  color: var(--status-teal);
}
.rp-time {
  font-size: 11px;
  color: var(--text-secondary);
  margin-left: auto;
}
.rp-content {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-primary);
}
</style>
