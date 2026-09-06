<script setup lang="ts" generic="TRow extends Record<string, unknown>">
/**
 * DataTable — generische Tabelle für Agora Design v4
 * Source-Truth: ds-screens-a.jsx :: DSA.LLMRouting (Stage-Overrides-Tabelle)
 * Slice D · 2026-05-11
 */

import { computed, useSlots } from 'vue'

export interface DataTableColumn {
  key: string
  label: string
  align?: 'left' | 'right' | 'center'
  width?: string
  /** Monospace-Render für Bezeichner wie Stage-Namen, Model-IDs */
  mono?: boolean
  /** Gedimmte Sekundärfarbe, z. B. für Provider/Effort-Spalten */
  secondary?: boolean
}

const props = withDefaults(
  defineProps<{
    columns: DataTableColumn[]
    rows: TRow[]
    /** Primär-Key-Feld für :key-Binding. Fallback: 'key', dann Index */
    keyField?: string
    rowClick?: (row: TRow) => void
    hover?: boolean
    /** Sticky-Header */
    sticky?: boolean
    /** Engerer Padding-Modus */
    compact?: boolean
    /** Markiert eine Zeile als ausgewählt (Accent-Tint + Kupfer-Kante links). */
    rowSelected?: (row: TRow) => boolean
  }>(),
  {
    keyField: 'id',
    hover: true,
    sticky: true,
    compact: false,
    rowSelected: undefined,
  },
)

defineSlots<{
  // cell-{key} Slots — TypeScript kann dynamische Slot-Namen nicht vollständig typisieren,
  // aber wir nutzen $slots zur Runtime-Prüfung.
  [key: string]: (props: { row: TRow; value: unknown; index: number }) => unknown
  actions: (props: { row: TRow; index: number }) => unknown
  empty: () => unknown
}>()

function rowKey(row: TRow, index: number): string | number {
  const pk = props.keyField
  if (pk in row && row[pk] !== undefined && row[pk] !== null) {
    return String(row[pk])
  }
  if ('key' in row && row['key'] !== undefined) {
    return String(row['key'])
  }
  return index
}

function cellSlotName(key: string): string {
  return `cell-${key}`
}

/**
 * Tastaturbedienung fuer anklickbare Zeilen.
 *
 * `rowClick` haengte bislang nur an `@click` — eine `<tr>` ist nicht
 * fokussierbar, also war die Zeilenauswahl fuer Tastaturnutzer schlicht nicht
 * erreichbar (Befund am Redesign-PR 8, betraf alle drei Verbraucher: Ablage,
 * ActiveRunsCard, RecentReportsCard). Mit `rowClick` bekommt die Zeile
 * `tabindex="0"` und reagiert zusaetzlich auf Enter und Leertaste.
 *
 * Bewusst KEIN `role="button"` auf der `<tr>`: das nimmt der Zeile ihre
 * Tabellensemantik, und der Screenreader verliert Zeilen-/Spaltenbezug. Die
 * Zeile bleibt eine Zeile und wird lediglich fokussierbar.
 */
function onRowKeydown(event: KeyboardEvent, row: TRow): void {
  if (!props.rowClick) return
  if (event.key !== 'Enter' && event.key !== ' ' && event.key !== 'Spacebar') return
  // Leertaste scrollt sonst die Seite, waehrend die Zeile ausgewaehlt wird.
  event.preventDefault()
  props.rowClick(row)
}

function alignClass(align?: 'left' | 'right' | 'center'): string {
  if (align === 'right') return 'dt-cell--right'
  if (align === 'center') return 'dt-cell--center'
  return 'dt-cell--left'
}

const hasActions = computed(() => !!useSlots()['actions'])
</script>

<template>
  <div class="dt-wrapper">
    <table class="dt-table">
      <thead :class="{ 'dt-thead--sticky': sticky }">
        <tr class="dt-head-row">
          <th
            v-for="col in columns"
            :key="col.key"
            class="dt-th"
            :class="alignClass(col.align)"
            :style="col.width ? { width: col.width } : undefined"
          >
            {{ col.label }}
          </th>
          <!-- Actions-Spalten-Header (kein Label) -->
          <th v-if="hasActions" class="dt-th dt-th--actions" aria-label="Aktionen" />
        </tr>
      </thead>
      <tbody>
        <template v-if="rows.length === 0">
          <tr>
            <td :colspan="columns.length + (hasActions ? 1 : 0)" class="dt-empty-cell">
              <slot name="empty">
                <span class="dt-empty-default">Keine Daten</span>
              </slot>
            </td>
          </tr>
        </template>
        <template v-else>
          <tr
            v-for="(row, index) in rows"
            :key="rowKey(row, index)"
            class="dt-body-row"
            :class="{
              'dt-body-row--hover': hover,
              'dt-body-row--clickable': !!rowClick,
              'dt-body-row--compact': compact,
              'dt-body-row--selected': !!rowSelected && rowSelected(row),
            }"
            :aria-current="rowSelected && rowSelected(row) ? 'true' : undefined"
            :tabindex="rowClick ? 0 : undefined"
            @click="rowClick ? rowClick(row) : undefined"
            @keydown="onRowKeydown($event, row)"
          >
            <td
              v-for="col in columns"
              :key="col.key"
              class="dt-td"
              :class="[
                alignClass(col.align),
                {
                  'dt-td--mono': col.mono,
                  'dt-td--secondary': col.secondary,
                  'dt-td--compact': compact,
                },
              ]"
            >
              <slot
                v-if="$slots[cellSlotName(col.key)]"
                :name="cellSlotName(col.key)"
                :row="row"
                :value="row[col.key]"
                :index="index"
              />
              <template v-else>
                {{ row[col.key] ?? '' }}
              </template>
            </td>
            <td v-if="hasActions" class="dt-td dt-td--actions">
              <slot name="actions" :row="row" :index="index" />
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.dt-wrapper {
  width: 100%;
  overflow-x: auto;
}

.dt-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  font-family: var(--font-sans);
  color: var(--text-primary);
}

/* ── Header ─────────────────────────────────────────────────── */

.dt-head-row {
  color: var(--text-secondary);
}

/* label-Typo-Rolle (Audit §Typografie): Satzschrift, kein Uppercase. */
.dt-th {
  font-size: 11.5px;
  font-weight: 500;
  text-transform: none;
  letter-spacing: 0.02em;
  padding: var(--table-cell-py, 10px) var(--table-cell-px, 16px);
  color: var(--text-secondary);
  white-space: nowrap;
}

.dt-thead--sticky .dt-th {
  position: sticky;
  top: 0;
  background: var(--surface-elevated);
  z-index: 1;
  border-bottom: 1px solid var(--separator);
}

.dt-th--actions {
  width: 1%;
  white-space: nowrap;
}

/* ── Body ───────────────────────────────────────────────────── */

/* 36px-Zeilen, Hairline unten (Audit §Komponentenstil). compact fällt auf
   28px, siehe .dt-body-row--compact. */
.dt-body-row {
  height: 36px;
  border-bottom: 1px solid var(--separator);
  transition: background 80ms ease;
}

.dt-body-row--compact {
  height: 28px;
}

.dt-body-row--hover:hover {
  background: var(--bg-hover, var(--surface-hover));
}

.dt-body-row--clickable {
  cursor: pointer;
}

/* Die anklickbare Zeile ist fokussierbar (tabindex) und braucht deshalb einen
   sichtbaren Ring. Bewusst ohne `transition`: der Playwright-Fokuscheck misst
   nach einem einzigen requestAnimationFrame, unter einer Transition stuende
   der Ring dann noch nicht. `outline-offset` negativ, damit der Ring innerhalb
   der Zeile bleibt und die Hairline der Nachbarzeile nicht ueberdeckt. */
.dt-body-row--clickable:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

/* Selected: Accent-Tint + 2px Kupfer-Kante links (Audit §Komponentenstil). */
.dt-body-row--selected {
  background: var(--bg-selected, var(--accent-tint-bg));
  box-shadow: inset 2px 0 0 var(--accent);
}

.dt-body-row--selected.dt-body-row--hover:hover {
  background: var(--bg-selected, var(--accent-tint-bg));
}

/* Vertikales Padding ist 0, weil die Zeilenhöhe (36px / compact 28px) auf
   .dt-body-row liegt — Padding oben addierte sich sonst darauf und die Zeile
   wäre höher als die Dichte-Spec erlaubt. vertical-align zentriert den Inhalt
   in der Zeilenhöhe. */
.dt-td {
  padding: 0 var(--table-cell-px, 16px);
  vertical-align: middle;
}

.dt-td--mono {
  font-family: var(--font-mono);
  font-size: 13px;
}

.dt-td--secondary {
  color: var(--text-secondary);
}

.dt-td--actions {
  white-space: nowrap;
  text-align: right;
}

/* ── Alignment ──────────────────────────────────────────────── */

.dt-cell--left  { text-align: left; }
/* Tabellarische Ziffern für rechtsbündige Spalten, damit Zahlen stellenweise
   untereinander stehen. Die Mono-Familie hängt bewusst an col.mono
   (.dt-td--mono), nicht an der Ausrichtung: rechtsbündig heißt nicht
   zwangsläufig numerisch, und der Spaltenkopf bleibt in der label-Typo. */
.dt-cell--right {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.dt-cell--center { text-align: center; }

/* ── Empty State ────────────────────────────────────────────── */

.dt-empty-cell {
  padding: 32px 8px;
  text-align: center;
}

.dt-empty-default {
  color: var(--text-tertiary);
  font-size: 13px;
}
</style>
