<script setup lang="ts">
/**
 * NewItemsPill — "N neue Beitraege" in Feed und Diskurs.
 *
 * Slice UI-2b (#1713), docs/design/simulation-feed.md §2.6. Ersetzt die
 * stille Slide-in-Animation aus der alten StepSimulationFeedView und
 * uebernimmt das Prinzip von `.fc-pause-chip` (FeedColumn.vue).
 *
 * Auto-Verstecken nach 20s, wenn der Nutzer nicht klickt (§2.6). Ein neuer
 * Zaehlerstand (count-Aenderung) startet den Timer neu.
 */
import { watch, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ count: number; visible: boolean }>()
const { t } = useI18n()
const emit = defineEmits<{ click: [] }>()

const AUTO_HIDE_MS = 20_000
let hideTimer: ReturnType<typeof setTimeout> | null = null

function clearTimer(): void {
  if (hideTimer) {
    clearTimeout(hideTimer)
    hideTimer = null
  }
}

watch(
  () => [props.visible, props.count] as const,
  ([visible]) => {
    clearTimer()
    if (visible) {
      hideTimer = setTimeout(() => emit('click'), AUTO_HIDE_MS)
    }
  },
  { immediate: true },
)

onBeforeUnmount(clearTimer)

function onClick(): void {
  clearTimer()
  emit('click')
}
</script>

<template>
  <Transition name="nip-pop">
    <button v-if="visible && count > 0" type="button" class="nip-root" @click="onClick">
      {{ t('feed.newItems', { count }) }}
    </button>
  </Transition>
</template>

<style scoped>
.nip-root {
  position: sticky;
  top: 8px;
  left: 50%;
  transform: translateX(-50%);
  margin: 0 auto 8px;
  display: block;
  border: 1px solid var(--hairline);
  border-radius: var(--r-pill);
  background: var(--surface-base);
  box-shadow: var(--sim-pill-shadow);
  padding: 5px 14px;
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
  cursor: pointer;
  z-index: 5;
}
.nip-root:hover {
  background: var(--surface-hover);
}
.nip-pop-enter-active,
.nip-pop-leave-active {
  transition: opacity 200ms ease, transform 200ms ease;
}
.nip-pop-enter-from,
.nip-pop-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-6px);
}
@media (prefers-reduced-motion: reduce) {
  .nip-pop-enter-active,
  .nip-pop-leave-active {
    transition: none;
  }
}
</style>
