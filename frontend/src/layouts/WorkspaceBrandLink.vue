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
  min-width: 0;
  gap: var(--sp-2, 8px);
  min-height: var(--ctl-h-md, 32px);
  padding: 0 var(--sp-2, 8px);
  background: transparent;
  border: 0;
  border-radius: var(--r-4, var(--r-1));
  cursor: pointer;
  font-family: var(--font-sans, var(--ff-sans));
  font-weight: 600;
  font-size: var(--fs-headline, var(--fs-18));
  line-height: 1;
  letter-spacing: 0;
  color: var(--text-primary, var(--fg));
  transition: background 120ms ease, color 120ms ease;
}

.workspace-brand-link:hover {
  background: var(--surface-hover, rgba(0,0,0,0.04));
  color: var(--accent);
}

.workspace-brand-link:focus-visible {
  outline: 2px solid var(--focus-ring, var(--accent));
  outline-offset: 2px;
}

.workspace-brand-link .wordmark {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1;
}

.workspace-brand-link .wordmark :deep(.dot),
.workspace-brand-link .wordmark .dot { color: var(--accent); }
</style>
