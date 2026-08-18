<template>
  <button
    v-if="count > 0"
    class="sticky-banner"
    :title="$t('common.scrollToBottom')"
    @click="$emit('jump')"
  >
    <span class="arrow" aria-hidden="true">↓</span>
    <span class="label">{{ $t('step3.feed.unread', count) }}</span>
  </button>
</template>

<script setup>
defineProps({
  count: { type: Number, default: 0 },
})
defineEmits(['jump'])
</script>

<style scoped>
.sticky-banner {
  position: absolute;
  left: 50%;
  bottom: var(--s-3);
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  padding: 8px 18px;
  background: linear-gradient(180deg,
    color-mix(in oklch, var(--accent) 100%, white 12%),
    var(--accent));
  color: var(--accent-ink);
  border: 1px solid color-mix(in oklch, var(--accent) 40%, transparent);
  border-radius: var(--r-pill);
  font-family: var(--ff-mono);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  cursor: pointer;
  z-index: 5;
  box-shadow:
    0 1px 0 0 color-mix(in oklch, white 35%, transparent) inset,
    0 8px 24px -6px var(--accent-glow),
    var(--shadow-1);
  transition: transform 120ms cubic-bezier(.2,.8,.2,1),
              box-shadow 160ms ease;
}

.sticky-banner:hover {
  transform: translateX(-50%) translateY(-2px);
  box-shadow:
    0 1px 0 0 color-mix(in oklch, white 40%, transparent) inset,
    0 14px 32px -6px var(--accent-glow),
    var(--shadow-2);
}

.arrow {
  font-weight: 700;
  font-size: 13px;
  line-height: 1;
}

.label {
  white-space: nowrap;
}
</style>
