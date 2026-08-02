<script setup lang="ts">
/**
 * Alert — inline-Banner für Hinweise, Fehler, Erfolge in Agora Design v4
 * Slice UI-F · 2026-05-15
 *
 * Tones: info | success | warning | danger
 * - info → blau (--accent), neutrale Hinweise
 * - success → grün (--status-green), positive Bestätigung
 * - warning → orange (--status-orange), aufmerksamkeitsbedürftig
 * - danger → rot (--status-red), Fehler/Abbruch
 *
 * Dismiss-Button optional via `dismissible`. Emits `dismiss` beim Schließen.
 * Slot `actions` für Folgeaktionen (z. B. Retry-Button).
 */

withDefaults(
  defineProps<{
    tone?: 'info' | 'success' | 'warning' | 'danger'
    title?: string
    dismissible?: boolean
    /** ARIA-Label für den Schließen-Button; per Default deutsch, i18n-fähig */
    dismissLabel?: string
  }>(),
  {
    tone: 'info',
    title: undefined,
    dismissible: false,
    dismissLabel: 'Schließen',
  },
)

defineEmits<{
  dismiss: []
}>()

defineSlots<{
  default: () => unknown
  actions: () => unknown
}>()
</script>

<template>
  <div
    class="al-root"
    :class="`al-root--${tone}`"
    role="alert"
    aria-live="polite"
  >
    <div class="al-icon" aria-hidden="true">
      <!-- Tone-spezifische SVGs: minimalistisch, monochrom über currentColor -->
      <svg
        v-if="tone === 'info'"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="16" x2="12" y2="12" />
        <line x1="12" y1="8" x2="12.01" y2="8" />
      </svg>
      <svg
        v-else-if="tone === 'success'"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M20 6 9 17l-5-5" />
      </svg>
      <svg
        v-else-if="tone === 'warning'"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
        <line x1="12" y1="9" x2="12" y2="13" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
      <svg
        v-else
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <circle cx="12" cy="12" r="10" />
        <line x1="15" y1="9" x2="9" y2="15" />
        <line x1="9" y1="9" x2="15" y2="15" />
      </svg>
    </div>

    <div class="al-body">
      <p v-if="title" class="al-title">{{ title }}</p>
      <p v-if="$slots.default" class="al-text">
        <slot />
      </p>
      <div v-if="$slots.actions" class="al-actions">
        <slot name="actions" />
      </div>
    </div>

    <button
      v-if="dismissible"
      type="button"
      class="al-dismiss"
      :aria-label="dismissLabel"
      @click="$emit('dismiss')"
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.al-root {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: var(--r-3, 6px);
  border: 1px solid var(--hairline);
  background: var(--surface-elevated);
  font-family: var(--font-sans);
  font-size: 13px;
  line-height: 1.45;
  color: var(--text-primary);
}

.al-icon {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  margin-top: 1px;
}

.al-body {
  flex: 1 1 auto;
  min-width: 0;
}

.al-title {
  margin: 0;
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
}

.al-text {
  margin: 2px 0 0;
  color: var(--text-secondary);
}

/* WCAG AA (#978): auf den getoenten Varianten-Hintergruenden reicht
   --text-secondary nicht mehr — gemessen 4.43:1 (warning) bzw. 4.34:1
   (danger) gegen die geforderten 4.5:1. Der neutrale .al-root-Hintergrund
   bleibt bei --text-secondary; nur die getoenten Flaechen heben auf
   --text-primary an (14.7:1 bzw. 14.4:1). info/success tragen dieselbe
   10%-Toenung und werden bewusst mitgezogen, statt auf den naechsten
   Zufallsfund zu warten. */
.al-root--info .al-text,
.al-root--success .al-text,
.al-root--warning .al-text,
.al-root--danger .al-text {
  color: var(--text-primary);
}

.al-title + .al-text {
  margin-top: 2px;
}

.al-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}

.al-dismiss {
  flex: 0 0 auto;
  background: transparent;
  border: 0;
  cursor: pointer;
  color: var(--text-tertiary);
  padding: 2px;
  border-radius: var(--r-1, 3px);
  display: flex;
}

.al-dismiss:hover {
  color: var(--text-primary);
  background: var(--surface-hover);
}

.al-dismiss:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 1px;
}

/* ── Tone-Varianten ──────────────────────────────────────── */

.al-root--info {
  background: var(--accent-tint-bg);
  border-color: rgba(0, 102, 204, 0.2);
}
.al-root--info .al-icon {
  color: var(--accent);
}
.al-root--info .al-title {
  color: var(--accent-tint-text);
}

.al-root--success {
  background: var(--status-green-bg);
  border-color: rgba(36, 138, 61, 0.2);
}
.al-root--success .al-icon {
  color: var(--status-green);
}
.al-root--success .al-title {
  color: var(--status-green);
}

.al-root--warning {
  background: var(--status-orange-bg);
  border-color: rgba(178, 80, 0, 0.2);
}
.al-root--warning .al-icon {
  color: var(--status-orange);
}
.al-root--warning .al-title {
  color: var(--status-orange);
}

.al-root--danger {
  background: var(--status-red-bg);
  border-color: rgba(197, 41, 42, 0.2);
}
.al-root--danger .al-icon {
  color: var(--status-red);
}
.al-root--danger .al-title {
  color: var(--status-red);
}
</style>
