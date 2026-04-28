<template>
  <button
    type="button"
    class="workspace-brand-link"
    @click="$emit('navigate-home')"
  >
    <AgoraGlyph :size="22" />
    <span v-if="!$slots.default" class="wordmark">
      Agor<span class="dot">·</span>a
    </span>
    <span v-else class="wordmark">
      <slot />
    </span>
  </button>
</template>

<script setup>
import AgoraGlyph from '../components/ui/AgoraGlyph.vue'

defineEmits(['navigate-home'])
</script>

<style scoped>
.workspace-brand-link {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 0;
  background: transparent;
  border: 0;
  cursor: pointer;
  font-family: var(--ff-serif);
  font-weight: 500;
  font-size: 20px;
  letter-spacing: -0.02em;
  color: var(--fg);
  transition: color 120ms ease;
}

.workspace-brand-link:hover { color: var(--accent); }
.workspace-brand-link .wordmark { line-height: 1; }
.workspace-brand-link .wordmark :deep(.dot),
.workspace-brand-link .wordmark .dot { color: var(--accent); }
</style>
