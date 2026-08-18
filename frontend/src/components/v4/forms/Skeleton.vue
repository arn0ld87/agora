<script setup lang="ts">
/**
 * Skeleton — Loading-Placeholder für Agora Design v4
 * Slice UI-D · 2026-05-15
 *
 * Verwendung:
 *   <Skeleton variant="text" />              // 1em-hohe Text-Zeile
 *   <Skeleton variant="text" :lines="3" />   // 3 gestaffelte Text-Zeilen
 *   <Skeleton variant="rect" height="120px" />
 *   <Skeleton variant="circle" size="40px" />
 *
 * Animationsmodus respektiert `prefers-reduced-motion: reduce`.
 */

withDefaults(
  defineProps<{
    /** Form des Platzhalters */
    variant?: 'text' | 'rect' | 'circle'
    /** Bei variant=text: Anzahl Zeilen (jede ~1em). Letzte Zeile leicht kürzer. */
    lines?: number
    /** CSS-Breite (rect/text) */
    width?: string
    /** CSS-Höhe (rect/text-Einzelzeile, default 1em / 14px) */
    height?: string
    /** Bei variant=circle: Durchmesser (rect-shape-Fallback width=height) */
    size?: string
  }>(),
  {
    variant: 'rect',
    lines: 1,
    width: '100%',
    height: '14px',
    size: '32px',
  },
)
</script>

<template>
  <div
    v-if="variant === 'text'"
    class="sk-stack"
    role="status"
    aria-busy="true"
    aria-live="polite"
  >
    <span
      v-for="i in lines"
      :key="i"
      class="sk sk--text"
      :style="{
        width: i === lines && lines > 1 ? '70%' : width,
      }"
    />
    <span class="sk-sr-only">Lade…</span>
  </div>

  <span
    v-else-if="variant === 'circle'"
    class="sk sk--circle"
    role="status"
    aria-busy="true"
    aria-live="polite"
    :style="{ width: size, height: size }"
  >
    <span class="sk-sr-only">Lade…</span>
  </span>

  <span
    v-else
    class="sk sk--rect"
    role="status"
    aria-busy="true"
    aria-live="polite"
    :style="{ width, height }"
  >
    <span class="sk-sr-only">Lade…</span>
  </span>
</template>

<style scoped>
.sk {
  display: inline-block;
  background: linear-gradient(
    90deg,
    var(--surface-inset) 0%,
    var(--surface-hover) 50%,
    var(--surface-inset) 100%
  );
  background-size: 200% 100%;
  animation: sk-shimmer 1.4s ease-in-out infinite;
  border-radius: var(--r-2, 4px);
}

.sk--text {
  height: 0.85em;
  display: block;
  border-radius: var(--r-1, 3px);
}

.sk--circle {
  border-radius: 50%;
  vertical-align: middle;
}

.sk--rect {
  display: block;
  border-radius: var(--r-3, 6px);
}

.sk-stack {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}

.sk-sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

@keyframes sk-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sk {
    animation: none;
    background: var(--surface-inset);
  }
}
</style>
