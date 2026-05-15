<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  title: string
  channel: 'reddit' | 'twitter'
}>()

const { t } = useI18n()

const scrollEl = ref<HTMLElement | null>(null)
const anchorEl = ref<HTMLElement | null>(null)
const isPinned = ref(false)

let observer: IntersectionObserver | null = null

function scrollToBottom(): void {
  if (scrollEl.value) {
    scrollEl.value.scrollTop = scrollEl.value.scrollHeight
  }
  isPinned.value = false
}

onMounted(() => {
  if (!anchorEl.value) return
  observer = new IntersectionObserver(
    ([entry]) => {
      // Wenn der Anker sichtbar ist, ist Auto-Scroll aktiv.
      // Wenn er weg-gescrollt wurde, ist der User manuell oben → Pause.
      isPinned.value = !entry.isIntersecting
    },
    { root: scrollEl.value, threshold: 0.1 },
  )
  observer.observe(anchorEl.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
})
</script>

<template>
  <section
    class="fc-root"
    :data-channel="channel"
    role="feed"
    :aria-label="title"
    aria-busy="false"
  >
    <header class="fc-header">
      <div class="fc-title-row">
        <span class="fc-title">{{ title }}</span>
        <span class="fc-live-dot" aria-hidden="true"></span>
      </div>
    </header>

    <div ref="scrollEl" class="fc-scroll">
      <slot />
      <div ref="anchorEl" class="fc-anchor" aria-hidden="true"></div>
    </div>

    <Transition name="fc-pin">
      <button
        v-if="isPinned"
        type="button"
        class="fc-pause-chip"
        @click="scrollToBottom"
      >
        {{ t('common.scrollToBottom') }}
      </button>
    </Transition>
  </section>
</template>

<style scoped>
.fc-root {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--hairline, #e5e7eb);
  border-radius: 8px;
  overflow: hidden;
  background: var(--surface, #ffffff);
  min-height: 0;
  position: relative;
}
.fc-header {
  padding: 10px 14px;
  border-bottom: 1px solid var(--hairline, #e5e7eb);
  background: var(--surface-subtle, #f9fafb);
  flex-shrink: 0;
}
.fc-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.fc-title {
  font-weight: 700;
  font-size: 13px;
  color: var(--text-primary, #111827);
  letter-spacing: 0.02em;
}
.fc-live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--status-green, #10b981);
  animation: live-pulse 1.5s ease-in-out infinite;
}
@keyframes live-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.85); }
}
@media (prefers-reduced-motion: reduce) {
  .fc-live-dot {
    animation: none;
  }
}
.fc-scroll {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
  scroll-behavior: smooth;
}
.fc-anchor {
  height: 1px;
}
.fc-pause-chip {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--surface, #fff);
  border: 1px solid var(--hairline, #e5e7eb);
  border-radius: 20px;
  padding: 5px 14px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary, #6b7280);
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  white-space: nowrap;
  z-index: 10;
}
.fc-pause-chip:hover {
  background: var(--surface-hover, #f9fafb);
}
.fc-pin-enter-active,
.fc-pin-leave-active {
  transition: opacity 200ms, transform 200ms;
}
.fc-pin-enter-from,
.fc-pin-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(8px);
}
@media (prefers-reduced-motion: reduce) {
  .fc-pin-enter-active,
  .fc-pin-leave-active {
    transition: none;
  }
}
</style>
