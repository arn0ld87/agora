<script setup lang="ts">
/**
 * Button — typesafe v4-Port von components/ui/Btn.vue
 * Slice UI-A · 2026-05-15
 *
 * CSS-Klassen kommen aus assets/styles/global.css (.btn, .btn--*).
 * Diese Komponente ist ein dünner typesafe Vue-Wrapper, damit neue v4-Code-
 * Pfade nicht das Legacy-Component aus components/ui/ importieren müssen.
 *
 * Vergleich zu ui/Btn.vue:
 * - TypeScript-Literale für variant/size statt String (verhindert Typos)
 * - defineEmits<{click}> typed
 * - loading wird automatisch disabled
 * - icon-only-Mode + aria-label-Pflicht
 */

export type ButtonVariant =
  | 'primary'
  | 'secondary'
  | 'ghost'
  | 'tinted'
  | 'accent'
  | 'info'
  | 'plasma'
  | 'glass'
  | 'danger'

export type ButtonSize = 'sm' | 'md' | 'lg'

const props = withDefaults(
  defineProps<{
    variant?: ButtonVariant
    size?: ButtonSize
    type?: 'button' | 'submit' | 'reset'
    disabled?: boolean
    loading?: boolean
    /** Icon-Only-Modus — Komponente nimmt nur Slot, runder Padding */
    icon?: boolean
    /** Pfeil-Glyph rechts (z. B. „Weiter →“) */
    arrow?: boolean
    /** Pflicht im icon-Modus für a11y; siehe Dev-Warn unten */
    ariaLabel?: string
  }>(),
  {
    variant: 'primary',
    size: 'md',
    type: 'button',
    disabled: false,
    loading: false,
    icon: false,
    arrow: false,
    ariaLabel: undefined,
  },
)

// Dev-only A11y-Guardrail: icon-only-Buttons brauchen einen accessible name.
// Per Default ist der Default-Slot bei icon=true ein SVG ohne Text — wenn auch
// ariaLabel fehlt, hat der Screenreader nichts zum Vorlesen.
if (import.meta.env.DEV && props.icon && !props.ariaLabel) {
  console.warn(
    '[v4/Button] icon=true erfordert ariaLabel für Screenreader-Kompatibilität.',
  )
}

defineEmits<{
  click: [event: MouseEvent]
}>()
</script>

<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    :aria-busy="loading ? 'true' : undefined"
    :aria-label="ariaLabel"
    class="btn v4-state-interactive"
    :class="[
      `btn--${variant}`,
      size !== 'md' && `btn--${size}`,
      icon && 'btn--icon',
      { 'is-loading': loading },
    ]"
    @click="$emit('click', $event)"
  >
    <slot />
    <span v-if="arrow" class="arrow" aria-hidden="true">→</span>
    <span v-if="loading" class="btn-spinner" aria-hidden="true" />
  </button>
</template>

<style scoped>
/* v4-state-interactive setzt border: 1px solid; .btn-Varianten übersteuern
   das über höhere Spezifität in global.css — kein Konflikt. */

.btn-spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  margin-left: 6px;
  border: 1.5px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: v4-btn-spin 0.7s linear infinite;
  vertical-align: middle;
}

@keyframes v4-btn-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .btn-spinner {
    animation: none;
    border-top-color: currentColor;
    opacity: 0.5;
  }
}
</style>
