<script setup>
defineProps({
  variant: { type: String, default: 'outline' },
  dot: { type: Boolean, default: false },
})
</script>

<template>
  <span class="badge" :class="`badge--${variant}`">
    <span v-if="dot" class="dot" />
    <slot />
  </span>
</template>
