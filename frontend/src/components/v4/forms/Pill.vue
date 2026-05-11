<script setup lang="ts">
/**
 * Pill — Alias für Badge.
 * Das DS verwendet beide Namen (badge/pill) austauschbar.
 * Technisch identisch mit Badge.vue — eigene Datei für expliziten Import.
 */
import Badge from './Badge.vue'

withDefaults(defineProps<{
  tone?: 'green' | 'orange' | 'red' | 'purple' | 'teal' | 'blue' | 'gray'
  dot?: boolean
}>(), {
  tone: 'gray',
  dot: true,
})
</script>

<template>
  <Badge :tone="tone" :dot="dot">
    <slot />
  </Badge>
</template>
