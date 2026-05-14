<template>
  <svg :width="size" :height="size" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
    <line x1="10" y1="4" x2="10" y2="16" stroke="currentColor" :stroke-width="stroke" stroke-linecap="round"/>
    <line x1="4" y1="10" x2="16" y2="10" stroke="currentColor" :stroke-width="stroke" stroke-linecap="round"/>
  </svg>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ size?: number; stroke?: number }>(), { size: 18, stroke: 1.6 })
</script>
