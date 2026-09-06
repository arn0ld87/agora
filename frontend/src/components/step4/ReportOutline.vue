<script setup lang="ts">
/**
 * ReportOutline — linke Spalte der Leseumgebung (PR 6, Premium-Redesign).
 *
 * Ersetzt fuer die abgeschlossene Leseansicht die lineare Formular-Optik aus
 * dem Audit ("Bericht als Formular-Stack", Problem #4): eine im Viewport
 * fixierte Outline-Navigation mit Sprungmarken zur Zusammenfassung, jedem
 * Abschnitt und dem Anhang (Hypothesen/Datenluecken/Belege/Red-Team-Zaehler).
 *
 * Rollenwahl (Briefing, Fallstrick 2): `role="tablist"`/`role="tab"` mit
 * `aria-selected`, weil es sich um eine Auswahl aus einer Menge alternativer
 * Ansichten handelt (jeweils genau ein Abschnitt sichtbar/aktiv) — nicht
 * `role="table"`/`"grid"`, wo `aria-selected` unzulaessig waere.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ReportReaderTestId } from '@/contracts/testIds'

export interface ReportOutlineItem {
  id: string
  num: string
  label: string
}

const props = defineProps<{
  items: ReportOutlineItem[]
  activeId: string
  sectionsCount: number
  hypothesesCount: number
  dataGapsCount: number
  evidenceCount: number
  redTeamCount: number
}>()

const emit = defineEmits<{
  navigate: [id: string]
}>()

const { t } = useI18n()

const testIds = ReportReaderTestId

function select(id: string) {
  emit('navigate', id)
}

function onKeydown(event: KeyboardEvent) {
  const key = event.key
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(key)) return
  event.preventDefault()
  const currentIndex = props.items.findIndex((item) => item.id === props.activeId)
  let nextIndex = currentIndex
  if (key === 'ArrowDown') nextIndex = Math.min(props.items.length - 1, currentIndex + 1)
  if (key === 'ArrowUp') nextIndex = Math.max(0, currentIndex - 1)
  if (key === 'Home') nextIndex = 0
  if (key === 'End') nextIndex = props.items.length - 1
  const next = props.items[nextIndex]
  if (!next) return
  select(next.id)
  const target = document.getElementById(`report-reader-tab-${next.id}`)
  target?.focus()
}

const appendixRows = computed(() => [
  { key: 'appendixHypotheses', count: props.hypothesesCount },
  { key: 'appendixDataGaps', count: props.dataGapsCount },
  { key: 'appendixEvidence', count: props.evidenceCount },
  { key: 'appendixRedTeam', count: props.redTeamCount, warn: true },
])
</script>

<template>
  <nav class="outline" :data-testid="testIds.outline" :aria-label="t('step4.reader.outlineTitle')">
    <p class="outline-label">
      {{ t('step4.reader.outlineTitle') }} · {{ t('step4.reader.outlineSectionsCount', { count: sectionsCount }) }}
    </p>
    <div class="outline-list" role="tablist" :aria-label="t('step4.reader.outlineTitle')" @keydown="onKeydown">
      <button
        v-for="item in items"
        :id="`report-reader-tab-${item.id}`"
        :key="item.id"
        type="button"
        role="tab"
        class="outline-item"
        :class="{ 'is-active': activeId === item.id }"
        :aria-selected="activeId === item.id"
        :aria-controls="item.id"
        :tabindex="activeId === item.id ? 0 : -1"
        :data-testid="testIds.outlineItem"
        @click="select(item.id)"
      >
        <span class="outline-num">{{ item.num }}</span>
        <span class="outline-item-label">{{ item.label }}</span>
      </button>
    </div>
    <div class="outline-appendix">
      <p class="outline-label">{{ t('step4.reader.appendixTitle') }}</p>
      <div
        v-for="row in appendixRows"
        :key="row.key"
        class="appendix-row"
        :class="{ 'appendix-row--warn': row.warn && row.count > 0 }"
      >
        {{ t(`step4.reader.${row.key}`, { count: row.count }) }}
      </div>
    </div>
  </nav>
</template>

<style scoped>
.outline {
  border-right: 1px solid var(--border-default);
  padding: var(--s-5) 0;
  overflow-y: auto;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.outline-label {
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: var(--text-secondary);
  margin: 0;
  padding: 0 var(--s-4);
}
.outline-list {
  display: flex;
  flex-direction: column;
}
.outline-item {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  gap: 9px;
  padding: 7px var(--s-4);
  color: var(--text-secondary);
  font-family: var(--font-sans);
  font-size: 13px;
  border: none;
  border-left: 2px solid transparent;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.outline-item .outline-num {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint, var(--text-secondary));
}
.outline-item.is-active {
  color: var(--text-primary);
  font-weight: 600;
  background: var(--bg-selected);
  border-left-color: var(--accent-primary);
}
.outline-item.is-active .outline-num {
  color: var(--accent-primary);
}
.outline-item:focus-visible {
  outline: var(--v4-state-focus-ring-width, 2px) solid var(--v4-state-focus-ring, var(--accent-primary));
  outline-offset: -2px;
}
.outline-appendix {
  margin-top: var(--s-3);
  padding: var(--s-3) var(--s-4) 0;
  border-top: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.appendix-row {
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-secondary);
}
.appendix-row--warn {
  color: var(--status-error-text, var(--status-error));
}
</style>
