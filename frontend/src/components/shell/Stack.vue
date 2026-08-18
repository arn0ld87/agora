<template>
  <nav class="stack" :aria-label="t('shelf.stack')" :data-testid="ShellTestId.stack">
    <button
      type="button"
      class="stack__back"
      :data-testid="ShellTestId.stackBack"
      :disabled="props.current === null"
      :aria-label="t('shelf.back')"
      @click="emit('select', null)"
    >
      <span class="stack__back-glyph" aria-hidden="true">&#8249;</span>
      <span class="stack__back-label">{{ t('shelf.back') }}</span>
    </button>

    <span class="stack__kicker">{{ t('shelf.stack') }}</span>

    <ol class="stack__pills">
      <li>
        <button
          type="button"
          class="stack__pill"
          :class="{ 'stack__pill--active': props.current === null }"
          :aria-current="props.current === null ? 'true' : undefined"
          @click="emit('select', null)"
        >
          {{ t('shelf.title') }}
        </button>
      </li>
      <li v-for="entry in ring" :key="`${entry.kind}:${entry.id}`">
        <button
          type="button"
          class="stack__pill"
          :class="{ 'stack__pill--active': isActive(entry) }"
          :aria-current="isActive(entry) ? 'true' : undefined"
          :title="entry.title"
          @click="emit('select', { kind: entry.kind, id: entry.id })"
        >
          {{ entry.title }}
        </button>
      </li>
    </ol>
  </nav>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ShellTestId } from '../../contracts/testIds'
import type { ShelfObject, ShelfObjectKind } from '../../types/shelf'

/**
 * Stack.vue — der Stapel (Block B3): Chronik der zuletzt geoeffneten
 * Ablage-Objekte dieser Session, als Rueckweg-Leiste.
 *
 * Ring: max 8 Eintraege, in sessionStorage (ueberlebt Reload, nicht
 * den Tab-Schluss — bewusst kein localStorage, das waere eine globale
 * Chronik ueber Sessions hinweg, die niemand angefordert hat).
 *
 * `stackBack` (ShellTestId.stackBack) fuehrt IMMER zurueck zur Ablage-
 * Liste (select(null)) — das ist der Rueckweg unter 1100px, an dem das
 * Dossier die Vollflaeche belegt und es weder Hamburger noch Tab-
 * Leiste gibt (Systemregel 09-systemregeln.html). Die Pills daneben
 * sind der Schnellzugriff auf zuvor geoeffnete Objekte.
 */

interface StackEntry {
  kind: ShelfObjectKind
  id: string
  title: string
}

const props = defineProps<{ current: ShelfObject | null }>()
const emit = defineEmits<{
  select: [target: { kind: ShelfObjectKind; id: string } | null]
}>()

const { t } = useI18n()

const STORAGE_KEY = 'agora.shelf.stack'
const RING_MAX = 8

function hydrate(): StackEntry[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    return Array.isArray(parsed) ? (parsed as StackEntry[]) : []
  } catch {
    return []
  }
}

const ring = ref<StackEntry[]>(hydrate())

function persist(): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(ring.value))
  } catch {
    /* sessionStorage kann fehlen (Tests, Private Mode) — Ring gilt nur im Speicher */
  }
}

function isActive(entry: StackEntry): boolean {
  return props.current !== null && props.current.kind === entry.kind && props.current.id === entry.id
}

watch(
  () => props.current,
  (obj) => {
    if (!obj) return
    const withoutDup = ring.value.filter((e) => !(e.kind === obj.kind && e.id === obj.id))
    ring.value = [...withoutDup, { kind: obj.kind, id: obj.id, title: obj.title }].slice(-RING_MAX)
    persist()
  },
  { immediate: true },
)
</script>

<style scoped>
.stack {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.stack__back {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 24px;
  padding: 0 8px 0 4px;
  border: 1px solid transparent;
  border-radius: var(--r-3);
  background: transparent;
  color: var(--text-secondary);
  font-family: var(--font-sans);
  font-size: var(--fs-caption-1);
  cursor: pointer;
  flex-shrink: 0;
}

.stack__back:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--surface-hover);
}

.stack__back:disabled {
  opacity: var(--v4-state-disabled-opacity, 0.45);
  cursor: default;
}

.stack__back:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.stack__back-glyph {
  font-size: 14px;
  line-height: 1;
}

.stack__kicker {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.stack__pills {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
  list-style: none;
  margin: 0;
  padding: 0;
}

.stack__pill {
  display: inline-flex;
  align-items: center;
  height: 24px;
  max-width: 220px;
  padding: 0 9px;
  border: 1px solid transparent;
  border-radius: var(--r-3);
  background: transparent;
  color: var(--text-tertiary);
  font-family: var(--font-sans);
  font-size: var(--fs-caption-1);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
}

.stack__pill:hover {
  color: var(--text-primary);
  background: var(--surface-hover);
}

.stack__pill--active {
  background: var(--accent-tint-bg);
  color: var(--accent-tint-text);
}

.stack__pill:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* Unter 1100px ist der Stapel der Rueckweg (Systemregel 09-systemregeln.html):
   die Pill-Chronik tritt zurueck, der Rueckweg-Knopf wird die Hauptaktion. */
@media (max-width: 1099px) {
  .stack__pills {
    display: none;
  }
  .stack__kicker {
    display: none;
  }
  .stack__back {
    height: 28px;
    padding: 0 10px 0 6px;
    border-color: var(--hairline);
  }
}

@media (prefers-reduced-motion: reduce) {
  .stack__back,
  .stack__pill {
    transition: none;
  }
}
</style>
