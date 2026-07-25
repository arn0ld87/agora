<script setup lang="ts">
import { computed } from 'vue'
import { A26_PROV_LABEL } from '../icons'

const props = withDefaults(defineProps<{ prov?: string }>(), { prov: 'ollama' })
const label = computed(() => A26_PROV_LABEL[props.prov] ?? '·')
</script>

<template>
  <span class="a26-prov-mark" :class="prov">{{ label }}</span>
</template>
