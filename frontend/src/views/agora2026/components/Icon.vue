<script setup lang="ts">
import { computed } from 'vue'
import { A26_ICONS } from '../icons'

const props = defineProps<{ name: string }>()
const svg = computed(() => A26_ICONS[props.name] ?? '')
</script>

<template>
  <span class="a26-icon" v-html="svg" aria-hidden="true" />
</template>

<style scoped>
.a26-icon { display: inline-flex; align-items: center; }
.a26-icon :deep(svg) { display: block; }
</style>
