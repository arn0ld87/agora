<template>
  <svg :width="size" :height="size" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M2 5C2 4.45 2.45 4 3 4H8L10 6H17C17.55 6 18 6.45 18 7V15C18 15.55 17.55 16 17 16H3C2.45 16 2 15.55 2 15V5Z"
      stroke="currentColor" :stroke-width="stroke" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ size?: number; stroke?: number }>(), { size: 18, stroke: 1.6 })
</script>
