<template>
  <svg :width="size" :height="size" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="3" y="4" width="14" height="12" rx="1.5"
      stroke="currentColor" :stroke-width="stroke" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="6" y1="8" x2="14" y2="8" stroke="currentColor" :stroke-width="stroke" stroke-linecap="round"/>
    <line x1="6" y1="11.5" x2="11" y2="11.5" stroke="currentColor" :stroke-width="stroke" stroke-linecap="round"/>
  </svg>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ size?: number; stroke?: number }>(), { size: 18, stroke: 1.6 })
</script>
