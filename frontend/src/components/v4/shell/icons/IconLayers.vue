<template>
  <svg :width="size" :height="size" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M10 3L17 7L10 11L3 7L10 3Z"
      stroke="currentColor" :stroke-width="stroke" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M3 11L10 15L17 11"
      stroke="currentColor" :stroke-width="stroke" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ size?: number; stroke?: number }>(), { size: 18, stroke: 1.6 })
</script>
