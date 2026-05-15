<script setup lang="ts">
/**
 * Kicker — Mono-Caption-Heading für Agora Design v4
 * Slice UI-C · 2026-05-15
 *
 * Ersetzt langfristig components/ui/Kicker.vue. Identische API-Erweiterung:
 * - Typesafe Props (TS statt JS)
 * - v4-Tokens (--font-mono, --fs-caption-1, --text-secondary, --accent)
 * - Optional `num` für Numerierung (z. B. "№ 03 —")
 */

withDefaults(
  defineProps<{
    /** Numerierungs-Präfix (z. B. "03") */
    num?: string | number | null
    /** Akzentuiert in Accent-Farbe statt Sekundär-Grau */
    accent?: boolean
  }>(),
  {
    num: null,
    accent: false,
  },
)
</script>

<template>
  <div class="kk-root" :class="{ 'kk-root--accent': accent }">
    <span v-if="num !== null && num !== ''" class="kk-num">№ {{ num }} —</span>
    <span class="kk-text"><slot /></span>
  </div>
</template>

<style scoped>
.kk-root {
  font-family: var(--font-mono);
  font-size: var(--fs-caption-1, 11px);
  line-height: 1.3;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-secondary);
  display: inline-flex;
  gap: 6px;
  align-items: baseline;
}

.kk-root--accent {
  color: var(--accent);
}

.kk-num {
  font-weight: 500;
}

.kk-text {
  font-weight: 500;
}
</style>
