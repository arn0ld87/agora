<script setup lang="ts">
/**
 * Gliederung (links) des Bericht-Reiters (Etappe 5, #1804, Bauplan 4.6).
 *
 * Schnittstelle für andere Tickets:
 *   Prop   `activeSection: number | null`  gewählter Abschnitt (`?section=`)
 *   Emit   `select(index: number)`          Sprung zu Abschnitt `index` (1-basiert)
 *   Daten  `useRunReportContext().outline`  Abschnitte mit Zustand
 *   Slot   `footer`                         unter der Liste (Hypothesen, Datenlücken, Zähler)
 *
 * Der Zustand je Abschnitt steht als Text (fertig, fehlt, fehlgeschlagen, in
 * Arbeit); das Symbol und die Farbe kommen nur dazu.
 */
import { useI18n } from 'vue-i18n'
import { useRunReportContext } from '@/composables/run/report/useRunReport'
import type { SectionState } from '@/composables/run/report/reportSections'

defineProps<{ activeSection: number | null }>()
const emit = defineEmits<{ select: [index: number] }>()
const { t } = useI18n()
const ctx = useRunReportContext()

const GLYPH: Record<SectionState, string> = { ready: '✓', missing: '○', failed: '✕', pending: '…' }
</script>

<template>
  <nav class="rr-outline" :aria-label="t('views.run.report.outline.label')" data-testid="report-outline">
    <p v-if="ctx.outline.value.length === 0" class="rr-outline__empty" data-testid="report-outline-empty">
      {{ t('views.run.report.outline.empty') }}
    </p>
    <ol v-else class="rr-outline__list">
      <li v-for="entry in ctx.outline.value" :key="entry.index">
        <button
          type="button"
          class="rr-outline__item"
          :class="`rr-outline__item--${entry.state}`"
          :aria-current="activeSection === entry.index ? 'location' : undefined"
          :data-testid="`report-outline-item-${entry.index}`"
          :data-state="entry.state"
          @click="emit('select', entry.index)"
        >
          <span class="rr-outline__num">{{ entry.index }}</span>
          <span class="rr-outline__title">{{ entry.title }}</span>
          <span class="rr-outline__state">
            <span aria-hidden="true">{{ GLYPH[entry.state] }}</span>
            {{ t(`views.run.report.outline.state.${entry.state}`) }}
          </span>
        </button>
      </li>
    </ol>
    <slot name="footer" />
  </nav>
</template>

<style scoped>
.rr-outline {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.rr-outline__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.rr-outline__item {
  display: grid;
  grid-template-columns: 22px 1fr;
  grid-template-areas: 'num title' '. state';
  gap: 0 6px;
  width: 100%;
  padding: 6px 8px;
  border: 0;
  border-radius: var(--ag-r-8);
  background: transparent;
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}
.rr-outline__item:hover {
  background: var(--s2);
}
.rr-outline__item:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.rr-outline__item[aria-current='location'] {
  background: var(--s3);
  font-weight: 650;
}
.rr-outline__num {
  grid-area: num;
  color: var(--fg3);
}
.rr-outline__title {
  grid-area: title;
  overflow-wrap: anywhere;
}
.rr-outline__state {
  grid-area: state;
  font-size: 12px;
  color: var(--fg2);
}
.rr-outline__item--missing .rr-outline__state,
.rr-outline__item--failed .rr-outline__state {
  color: var(--warn);
  font-weight: 600;
}
.rr-outline__item--failed .rr-outline__state {
  color: var(--err);
}
.rr-outline__empty {
  margin: 0;
  font-size: 13px;
  color: var(--fg2);
}
</style>
