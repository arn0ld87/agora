<template>
  <component
    :is="iconMap[name]"
    :size="size"
    :stroke="stroke"
  />
</template>

<script setup lang="ts">
import type { Component } from 'vue'
import IconHome from './icons/IconHome.vue'
import IconBolt from './icons/IconBolt.vue'
import IconFolder from './icons/IconFolder.vue'
import IconLayers from './icons/IconLayers.vue'
import IconDoc from './icons/IconDoc.vue'
import IconSpark from './icons/IconSpark.vue'
import IconSettings from './icons/IconSettings.vue'
import IconChevron from './icons/IconChevron.vue'
import IconChevronD from './icons/IconChevronD.vue'
import IconArrowL from './icons/IconArrowL.vue'
import IconSearch from './icons/IconSearch.vue'
import IconPlus from './icons/IconPlus.vue'
import IconMenu from './icons/IconMenu.vue'

export type IconName =
  | 'home'
  | 'bolt'
  | 'folder'
  | 'layers'
  | 'doc'
  | 'spark'
  | 'settings'
  | 'chevron'
  | 'chevronD'
  | 'arrowL'
  | 'search'
  | 'plus'
  | 'menu'
  // ds-shell.jsx aliases
  | 'branch'

const iconMap: Record<string, Component> = {
  home: IconHome,
  bolt: IconBolt,
  folder: IconFolder,
  layers: IconLayers,
  doc: IconDoc,
  spark: IconSpark,
  settings: IconSettings,
  chevron: IconChevron,
  chevronD: IconChevronD,
  arrowL: IconArrowL,
  search: IconSearch,
  plus: IconPlus,
  menu: IconMenu,
  // ds-shell.jsx uses "branch" for Runs — map to bolt as fallback
  branch: IconBolt,
}

const props = withDefaults(
  defineProps<{
    name: IconName | string
    size?: number
    stroke?: number
  }>(),
  { size: 18, stroke: 1.6 },
)

// Stille Fallback-Warnung in Dev
if (import.meta.env.DEV && !iconMap[props.name]) {
  console.warn(`[Icon] Unbekanntes Icon: "${props.name}" — kein SVG registriert.`)
}
</script>
