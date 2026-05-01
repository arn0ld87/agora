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
  padding: 6px 14px;
  background: var(--accent);
  color: var(--bg);
  border: 0;
  border-radius: var(--r-pill);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  cursor: pointer;
  z-index: 5;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.35);
  transition: transform 120ms ease, box-shadow 120ms ease;
}

.sticky-banner:hover {
  transform: translateX(-50%) translateY(-1px);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
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
