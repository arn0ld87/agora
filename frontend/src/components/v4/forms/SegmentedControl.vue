<script setup lang="ts">
/**
 * SegmentedControl — pill-förmiger Single-Choice-Schalter.
 *
 * ``disabled`` sperrt die Steuerung semantisch (nicht nur optisch): echte
 * ``disabled``-Attribute an den Buttons, ``tabindex="-1"`` aus dem Tab-Ring
 * heraus, ``aria-disabled="true"`` für assistive Technik und kein
 * ``update:modelValue``-Emit im gesperrten Zustand. Die Optik (aktives
 * Segment, Hover) bleibt erhalten; Hover wird nur für nicht-deaktivierte
 * Segmente gezeigt.
 */
const props = withDefaults(defineProps<{
  modelValue: string
  options: Array<{ value: string; label: string }>
  disabled?: boolean
}>(), {
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

function onSelect(value: string): void {
  if (props.disabled) return
  emit('update:modelValue', value)
}
</script>

<template>
  <div class="v4-segmented" role="group" :aria-disabled="disabled || undefined">
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      class="v4-segmented__seg v4-state-selectable"
      :class="{ 'v4-segmented__seg--active': modelValue === opt.value }"
      :disabled="disabled"
      :tabindex="disabled ? -1 : 0"
      :aria-disabled="disabled || undefined"
      @click="onSelect(opt.value)"
    >
      {{ opt.label }}
    </button>
  </div>
</template>

<style scoped>
.v4-segmented {
  display: inline-flex;
  background: var(--surface-inset, var(--gray-6, #f2f2f7));
  padding: 2px;
  border-radius: var(--r-pill, 999px);
  gap: 0;
}

.v4-segmented__seg {
  height: var(--ctl-h-sm, 28px);
  padding: 0 12px;
  border-radius: var(--r-pill, 999px);
  border: none;
  background: transparent;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: color 120ms ease, background 120ms ease, box-shadow 120ms ease;
  white-space: nowrap;
  line-height: 1;
}

/* Hover: v4-state-selectable liefert BG; zusätzlich Farbe für inaktive Segmente.
   Deaktivierte Segmente zeigen keinen Hover-Effekt. */
.v4-segmented__seg:hover:not(.v4-segmented__seg--active):not(:disabled) {
  color: var(--v4-state-hover-fg);
}

.v4-segmented__seg--active {
  background: #fff;
  box-shadow: var(--shadow-control, 0 1px 3px rgba(0, 0, 0, 0.12), 0 0 0 0.5px rgba(0, 0, 0, 0.04));
  color: var(--text-secondary);
}

/* Disabled: Cursor zurücksetzen; Optik (inkl. active-Segment) bleibt erhalten.
   pointer-events wird bewusst NICHT auf none gesetzt, damit Hover-States
   kontrolliert über :not(:disabled) laufen und die Steuerung semantisch
   greifbar bleibt (Tab-Skip via tabindex=-1, aria-disabled). */
.v4-segmented__seg:disabled {
  cursor: default;
}
</style>