<script setup lang="ts">
/**
 * Dialog — modaler Container mit Focus-Trap und Scroll-Lock für Agora Design v4
 * Slice UI-E · 2026-05-15
 *
 * Use-Case: Confirm-Dialoge (Run löschen, Reset), Settings-Sub-Panels,
 * Persona-Detail-Inspector.
 *
 * Verhalten:
 * - `v-model` (boolean) steuert das Offen-Sein.
 * - Open: scrollt body sperren, Fokus auf erstes fokussierbares Element im Panel.
 * - ESC schließt; Backdrop-Click schließt (sofern dismissible nicht false).
 * - Tab/Shift+Tab werden im Panel zyklisch gefangen (einfacher Focus-Trap).
 * - Close: Fokus geht zurück auf das ursprünglich fokussierte Element.
 *
 * Bewusst kein Teleport-to-body, weil AppShell schon top-level rendert. Wer
 * das Dialog tief im Komponentenbaum mountet, kann es als Wrapper umgeben.
 */

import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    /** v-model: open-State */
    modelValue: boolean
    /** Titel über dem Body */
    title?: string
    /** Beschreibung unter dem Titel */
    description?: string
    /** ARIA-Label, falls kein sichtbarer Titel */
    ariaLabel?: string
    /** Erlaubt ESC + Backdrop-Click? (Confirms „nicht wegklickbar" → false) */
    dismissible?: boolean
    /** Größenpresets */
    size?: 'sm' | 'md' | 'lg'
  }>(),
  {
    title: undefined,
    description: undefined,
    ariaLabel: undefined,
    dismissible: true,
    size: 'md',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  open: []
  close: []
}>()

defineSlots<{
  default: () => unknown
  footer: () => unknown
}>()

const panelRef = ref<HTMLElement | null>(null)
const previouslyFocused = ref<HTMLElement | null>(null)
// Vorherigen body.style.overflow-Wert speichern, damit beim Schließen kein
// fremder Scroll-Lock zurückgesetzt wird (z. B. wenn parent-Component bereits
// overflow:hidden gesetzt hatte).
const previousBodyOverflow = ref<string>('')

// Dev-only A11y-Guardrail: ohne sichtbaren title MUSS ariaLabel gesetzt sein,
// sonst hat das role="dialog" keinen accessible name.
if (import.meta.env.DEV && !props.title && !props.ariaLabel) {
  console.warn(
    '[v4/Dialog] entweder title oder ariaLabel ist Pflicht für role="dialog".',
  )
}

function close(): void {
  if (!props.modelValue) return
  emit('update:modelValue', false)
  emit('close')
}

function onBackdropClick(): void {
  if (props.dismissible) close()
}

function onKeydown(event: KeyboardEvent): void {
  if (!props.modelValue) return
  if (event.key === 'Escape' && props.dismissible) {
    event.preventDefault()
    close()
    return
  }
  if (event.key === 'Tab') {
    trapFocus(event)
  }
}

function focusableElements(root: HTMLElement): HTMLElement[] {
  const selector = [
    'a[href]',
    'button:not([disabled])',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
  ].join(',')
  return Array.from(root.querySelectorAll<HTMLElement>(selector)).filter(
    (el) => !el.hasAttribute('disabled') && el.offsetParent !== null,
  )
}

function trapFocus(event: KeyboardEvent): void {
  const panel = panelRef.value
  if (!panel) return
  const focusables = focusableElements(panel)
  if (focusables.length === 0) {
    event.preventDefault()
    panel.focus()
    return
  }
  const first = focusables[0]
  const last = focusables[focusables.length - 1]
  const active = document.activeElement as HTMLElement | null

  if (event.shiftKey && active === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && active === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(
  () => props.modelValue,
  async (open, previousOpen) => {
    if (open) {
      previouslyFocused.value = (document.activeElement as HTMLElement | null) ?? null
      previousBodyOverflow.value = document.body.style.overflow
      document.body.style.overflow = 'hidden'
      document.addEventListener('keydown', onKeydown)
      emit('open')
      await nextTick()
      const panel = panelRef.value
      if (panel) {
        const focusables = focusableElements(panel)
        ;(focusables[0] ?? panel).focus()
      }
    } else if (previousOpen) {
      // Nur aufräumen, wenn vorher offen war (verhindert Side-Effects bei
      // initial-mount mit modelValue=false). Restore-statt-Reset, damit
      // parent-seitige Scroll-Locks erhalten bleiben.
      document.body.style.overflow = previousBodyOverflow.value
      previousBodyOverflow.value = ''
      document.removeEventListener('keydown', onKeydown)
      previouslyFocused.value?.focus()
      previouslyFocused.value = null
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (props.modelValue) {
    document.body.style.overflow = previousBodyOverflow.value
  }
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <Transition name="dlg-fade">
    <div v-if="modelValue" class="dlg-overlay" @click.self="onBackdropClick">
      <div
        ref="panelRef"
        class="dlg-panel"
        :class="`dlg-panel--${size}`"
        role="dialog"
        aria-modal="true"
        :aria-label="ariaLabel"
        :aria-labelledby="title ? 'dlg-title' : undefined"
        :aria-describedby="description ? 'dlg-desc' : undefined"
        tabindex="-1"
      >
        <header v-if="title || description" class="dlg-header">
          <h2 v-if="title" id="dlg-title" class="dlg-title">{{ title }}</h2>
          <p v-if="description" id="dlg-desc" class="dlg-desc">{{ description }}</p>
        </header>

        <div class="dlg-body">
          <slot />
        </div>

        <footer v-if="$slots.footer" class="dlg-footer">
          <slot name="footer" />
        </footer>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.dlg-overlay {
  position: fixed;
  inset: 0;
  background: var(--surface-backdrop);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  z-index: 100;
}

.dlg-panel {
  background: var(--surface-elevated);
  border-radius: var(--r-4, 10px);
  box-shadow: var(--shadow-3);
  width: 100%;
  max-width: 520px;
  max-height: calc(100vh - 32px);
  display: flex;
  flex-direction: column;
  outline: none;
}

.dlg-panel--sm {
  max-width: 380px;
}

.dlg-panel--md {
  max-width: 520px;
}

.dlg-panel--lg {
  max-width: 720px;
}

.dlg-header {
  padding: 20px 24px 8px;
}

.dlg-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
}

.dlg-desc {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.45;
}

.dlg-body {
  padding: 16px 24px;
  overflow: auto;
  flex: 1 1 auto;
  font-size: 14px;
  color: var(--text-primary);
}

.dlg-footer {
  padding: 12px 24px 20px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px solid var(--separator);
}

.dlg-fade-enter-active,
.dlg-fade-leave-active {
  transition: opacity 140ms ease;
}

.dlg-fade-enter-from,
.dlg-fade-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .dlg-fade-enter-active,
  .dlg-fade-leave-active {
    transition: none;
  }
}
</style>
