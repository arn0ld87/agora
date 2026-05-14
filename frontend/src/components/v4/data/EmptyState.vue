<script setup lang="ts">
/**
 * EmptyState — generischer leerer Zustand für Agora Design v4
 * Slice D · 2026-05-11
 *
 * Icon-Anbindung: aktuell Inline-SVG (default: Tabellen-Icon).
 * Sobald Slice B Icon-Component liefert, kann via `icon`-Prop
 * auf deren Registry verwiesen werden.
 */

withDefaults(
  defineProps<{
    title?: string
    subtitle?: string
    /** Icon-Name-Stub — vorbereitet für Slice-B-Icon-Component */
    icon?: string
  }>(),
  {
    title: 'Keine Daten',
    subtitle: undefined,
    icon: 'table',
  },
)

defineSlots<{
  actions: () => unknown
}>()
</script>

<template>
  <div class="es-root">
    <!-- Inline-SVG: generisches Tabellen-Icon als Default -->
    <div class="es-icon" aria-hidden="true">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <path d="M3 9h18M3 15h18M9 3v18" />
      </svg>
    </div>

    <p class="es-title">{{ title }}</p>

    <p v-if="subtitle" class="es-subtitle">
      {{ subtitle }}
    </p>

    <div v-if="$slots.actions" class="es-actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped>
.es-root {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
  color: var(--text-secondary);
}

.es-icon {
  color: var(--text-quaternary);
  margin-bottom: 16px;
}

.es-title {
  margin: 0;
  font-size: 15px;
  font-weight: 500;
  font-family: var(--font-sans);
  color: var(--text-secondary);
}

.es-subtitle {
  margin: 6px 0 0;
  font-size: 13px;
  font-family: var(--font-sans);
  color: var(--text-tertiary);
  max-width: 320px;
  line-height: 1.5;
}

.es-actions {
  margin-top: 20px;
  display: flex;
  gap: 8px;
  justify-content: center;
}
</style>
