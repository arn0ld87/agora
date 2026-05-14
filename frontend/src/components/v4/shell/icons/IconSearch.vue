<template>
  <svg :width="size" :height="size" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="9" cy="9" r="5" stroke="currentColor" :stroke-width="stroke" stroke-linecap="round"/>
    <line x1="13" y1="13" x2="17" y2="17" stroke="currentColor" :stroke-width="stroke" stroke-linecap="round"/>
  </svg>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ size?: number; stroke?: number }>(), { size: 18, stroke: 1.6 })
</script>
