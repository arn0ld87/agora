<template>
  <svg :width="size" :height="size" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
    <line x1="3" y1="5" x2="17" y2="5" stroke="currentColor" :stroke-width="stroke" stroke-linecap="round"/>
    <line x1="3" y1="10" x2="17" y2="10" stroke="currentColor" :stroke-width="stroke" stroke-linecap="round"/>
    <line x1="3" y1="15" x2="17" y2="15" stroke="currentColor" :stroke-width="stroke" stroke-linecap="round"/>
  </svg>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ size?: number; stroke?: number }>(), { size: 18, stroke: 1.6 })
</script>
