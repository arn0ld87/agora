<template>
  <div v-if="props.objects.length > 0" class="activity">
    <button
      type="button"
      ref="triggerEl"
      class="activity__trigger"
      :data-testid="ShellTestId.activityIndicator"
      :aria-expanded="open"
      aria-haspopup="true"
      @click="toggle"
    >
      <span class="activity__dot" aria-hidden="true"></span>
      {{ t('shelf.activity', { n: props.objects.length }) }}
    </button>

    <div v-if="open" ref="panelEl" class="activity__panel" role="region" :aria-label="t('shelf.activity', { n: props.objects.length })">
      <ul class="activity__list">
        <li v-for="obj in props.objects" :key="`${obj.kind}:${obj.id}`" class="activity__item">
          <button type="button" class="activity__item-label" @click="selectObject(obj)">
            <span class="activity__item-tag">{{ SHELF_KIND_TAG[obj.kind] }}</span>
            <span class="activity__item-title">{{ obj.title }}</span>
          </button>
          <button
            type="button"
            class="activity__item-cancel"
            :data-testid="ShellTestId.activityCancel"
            :disabled="!obj.active"
            @click="obj.active && cancelAction.cancel(obj.active.runId)"
          >
            {{ t('shelf.cancel') }}
          </button>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ShellTestId } from '../../contracts/testIds'
import { SHELF_KIND_TAG, type ShelfObject, type ShelfObjectKind } from '../../types/shelf'
import { useCancelAction } from './useCancelAction'

/**
 * ActivityIndicator.vue — Topbar-Element (Block B3).
 *
 * Zeigt die Anzahl laufender/pausierter Objekte (useShelf.activeObjects).
 * Klick oeffnet eine kleine Liste mit Abbrechen je Eintrag — Abbrechen
 * laeuft ueber dieselbe 5s-Undo-Logik wie in Shelf/Dossier
 * (useCancelAction ist ein Singleton, siehe dort).
 */

const props = defineProps<{ objects: ShelfObject[] }>()
const emit = defineEmits<{ select: [target: { kind: ShelfObjectKind; id: string }] }>()

const { t } = useI18n()
const cancelAction = useCancelAction()
const open = ref(false)
const panelEl = ref<HTMLElement | null>(null)
const triggerEl = ref<HTMLButtonElement | null>(null)

function toggle(): void {
  open.value = !open.value
}

function selectObject(obj: ShelfObject): void {
  open.value = false
  emit('select', { kind: obj.kind, id: obj.id })
}

function onDocClick(e: MouseEvent): void {
  if (!open.value) return
  const target = e.target as Node
  if (panelEl.value && !panelEl.value.contains(target)) {
    // Trigger-Klicks steuert @click auf dem Button selbst (toggle) —
    // hier nur Klicks AUSSERHALB von Trigger+Panel abfangen.
    const trigger = (panelEl.value.previousElementSibling as HTMLElement) ?? null
    if (trigger && trigger.contains(target)) return
    open.value = false
  }
}

function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Escape' && open.value) {
    // Das Panel verschwindet aus dem DOM. Laege der Fokus darin, fiele
    // er auf den Dokumentkoerper — wer per Tastatur arbeitet, muesste
    // sich von vorn durch die Seite hangeln. Also zurueck zum Ausloeser.
    const trigger = triggerEl.value
    open.value = false
    void nextTick(() => trigger?.focus())
  }
}

onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
.activity {
  position: relative;
}

.activity__trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 25px;
  padding: 0 10px;
  border: 1px solid var(--hairline);
  border-radius: var(--r-pill);
  background: transparent;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 10.5px;
  letter-spacing: 0.05em;
  cursor: pointer;
}

.activity__trigger:hover {
  color: var(--text-primary);
  background: var(--surface-hover);
}

.activity__trigger:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.activity__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--status-teal);
}

.activity__panel {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 30;
  width: 280px;
  max-height: 320px;
  overflow-y: auto;
  background: var(--surface-elevated);
  border: 1px solid var(--hairline);
  border-radius: var(--r-5);
  box-shadow: var(--shadow-3);
  padding: 6px;
}

.activity__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.activity__item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px;
  border-radius: var(--r-3);
}

.activity__item-label {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
  padding: 4px;
  border-radius: var(--r-3);
}

.activity__item-label:hover {
  background: var(--surface-hover);
}

.activity__item-label:focus-visible,
.activity__item-cancel:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.activity__item-tag {
  font-family: var(--font-mono);
  font-size: 9.5px;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
  border: 1px solid var(--hairline);
  border-radius: var(--r-2);
  padding: 1px 4px;
  flex-shrink: 0;
}

.activity__item-title {
  font-size: var(--fs-caption-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.activity__item-cancel {
  flex-shrink: 0;
  height: 24px;
  padding: 0 8px;
  border: 1px solid var(--hairline);
  border-radius: var(--r-3);
  background: transparent;
  color: var(--text-secondary);
  font-family: var(--font-sans);
  font-size: 11px;
  cursor: pointer;
}

.activity__item-cancel:hover:not(:disabled) {
  color: var(--status-red);
  border-color: var(--status-red);
}

.activity__item-cancel:disabled {
  opacity: 0.4;
  cursor: default;
}
</style>
