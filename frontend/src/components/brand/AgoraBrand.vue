<template>
  <span class="agora-brand" :class="[`agora-brand--${mode}`, { 'agora-brand--inline': inline }]" :style="sizeStyle">
    <img
      :src="src"
      :alt="alt"
      :width="width"
      :height="height"
      class="agora-brand__img"
      draggable="false"
    />
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type BrandMode = 'glyph' | 'full-animated' | 'full-static'

const props = withDefaults(
  defineProps<{
    /** glyph: kompaktes Emblem ohne Wortmarke. full-animated: vollständig + Animation. full-static: vollständig ohne Animation. */
    mode?: BrandMode
    /** Höhe in px. Width skaliert proportional aus dem viewBox. */
    height?: number
    /** Aria-Label (Bild-Alt). */
    alt?: string
    /** Inline-display (für Text-Flow) statt block. */
    inline?: boolean
  }>(),
  {
    mode: 'full-animated',
    height: 80,
    alt: 'Agora',
    inline: false,
  },
)

// Assets liegen unter /brand/ (frontend/public/brand/*) — kein Vite-Import,
// damit sie unabhängig vom Bundling als statische Files ausliefert werden.
const ASSETS: Record<BrandMode, string> = {
  glyph: '/brand/agora-logo-glyph.svg',
  'full-animated': '/brand/agora-logo-animated.svg',
  'full-static': '/brand/agora-logo.png',
}

const ASPECT_RATIO: Record<BrandMode, number> = {
  // viewBox 320x320 (nur Emblem aus dem 960x320-Asset extrahiert)
  glyph: 1,
  // full-animated/full-static: viewBox 960x320 => 3:1
  'full-animated': 3,
  'full-static': 3,
}

const src = computed(() => ASSETS[props.mode])
const width = computed(() => Math.round(props.height * ASPECT_RATIO[props.mode]))
const height = computed(() => props.height)
const sizeStyle = computed(() => ({
  '--brand-height': `${props.height}px`,
}))
</script>

<style scoped>
.agora-brand {
  display: inline-flex;
  align-items: center;
  line-height: 0;
}
.agora-brand--inline {
  display: inline-flex;
  vertical-align: middle;
}
.agora-brand__img {
  display: block;
  height: var(--brand-height);
  width: auto;
  max-width: 100%;
  user-select: none;
}
</style>
