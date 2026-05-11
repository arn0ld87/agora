<template>
  <svg :width="size" :height="size" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M5 3H12L17 8V17H5V3Z"
      stroke="currentColor" :stroke-width="stroke" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M12 3V8H17"
      stroke="currentColor" :stroke-width="stroke" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="8" y1="11" x2="14" y2="11" stroke="currentColor" :stroke-width="stroke" stroke-linecap="round"/>
    <line x1="8" y1="14" x2="14" y2="14" stroke="currentColor" :stroke-width="stroke" stroke-linecap="round"/>
  </svg>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ size?: number; stroke?: number }>(), { size: 18, stroke: 1.6 })
</script>
