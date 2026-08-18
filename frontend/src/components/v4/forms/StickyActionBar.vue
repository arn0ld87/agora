<script setup lang="ts">
withDefaults(defineProps<{
  dirty?: boolean
}>(), {
  dirty: false,
})
</script>

<template>
  <div class="v4-sticky-bar" :class="{ 'v4-sticky-bar--dirty': dirty }">
    <div class="v4-sticky-bar__left">
      <slot name="left" />
    </div>

    <div class="v4-sticky-bar__right">
      <transition name="v4-dirty-hint">
        <span v-if="dirty" class="v4-sticky-bar__dirty-hint">
          Ungespeicherte Änderungen
        </span>
      </transition>
      <slot name="right" />
    </div>
  </div>
</template>

<style scoped>
.v4-sticky-bar {
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 24px;
  background: var(--surface-translucent);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-top: 1px solid var(--separator);
  box-shadow: 0 -8px 24px rgba(0, 0, 0, 0.04);
  z-index: 10;
}

.v4-sticky-bar__left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.v4-sticky-bar__right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.v4-sticky-bar__dirty-hint {
  font-family: var(--font-sans);
  font-size: 12.5px;
  color: var(--text-tertiary);
  font-weight: 400;
}

/* Transition */
.v4-dirty-hint-enter-active,
.v4-dirty-hint-leave-active {
  transition: opacity 200ms ease;
}
.v4-dirty-hint-enter-from,
.v4-dirty-hint-leave-to {
  opacity: 0;
}
</style>
