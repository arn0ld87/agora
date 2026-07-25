<script setup lang="ts">
import ProvMark from './ProvMark.vue'
import Icon from './Icon.vue'
import { A26_PROV_NAME } from '../icons'
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    provider?: string
    model?: string
    label?: string
  }>(),
  {
    provider: 'ollama',
    model: 'glm-5.1',
    label: 'Workspace',
  },
)

const provName = computed(() => A26_PROV_NAME[props.provider] ?? props.provider)
</script>

<template>
  <button type="button" class="a26-model-pill" :title="`Aktives Modell · ${label}`">
    <span class="mp-label">{{ label }}</span>
    <span class="mp-prov">
      <ProvMark :prov="provider" />
      <span style="font-size: 12px">{{ provName }}</span>
    </span>
    <span class="mp-model">
      <span class="a26-dot accent a26-pulse-live" />
      <span class="a26-mono" style="font-size: 11.5px">{{ model }}</span>
    </span>
    <span class="mp-caret"><Icon name="caret" /></span>
  </button>
</template>

<style scoped>
.a26-model-pill { font-family: inherit; }
</style>
