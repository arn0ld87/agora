<script setup>
defineProps({
  variant: { type: String, default: 'primary' },
  size: { type: String, default: 'md' },
  type: { type: String, default: 'button' },
  disabled: { type: Boolean, default: false },
  arrow: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  icon: { type: Boolean, default: false },
})
</script>

<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    class="btn"
    :class="[
      `btn--${variant}`,
      size !== 'md' && `btn--${size}`,
      icon && 'btn--icon',
      { 'is-loading': loading },
    ]"
  >
    <slot />
    <span v-if="arrow" class="arrow">→</span>
    <span v-if="loading" class="spinner" aria-hidden="true" />
  </button>
</template>

<style scoped>
.spinner {
  width: 12px;
  height: 12px;
  border: 1.5px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: btn-spin 0.7s linear infinite;
}
@keyframes btn-spin { to { transform: rotate(360deg); } }
</style>
