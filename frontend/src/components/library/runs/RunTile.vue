<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { entryTarget, type RunEntry } from '@/composables/library/runState'
import type { VersionsState } from '@/composables/library/useLibraryRuns'
import { formatShelfDate, jobStatusMessage } from '@/composables/useShelf'
import RunStageDots from './RunStageDots.vue'
import RunStateMark from './RunStateMark.vue'
import RunVersionsList from './RunVersionsList.vue'
import { reportLink } from '@/utils/reportRoute'

/**
 * Lauf als Kachel oder Listenzeile (dieselben Angaben, anderes Raster).
 * Der Titel ist ein Link ueber die ganze Flaeche (RunOverview); Auswahl,
 * Fassungen-Knopf und „Juengste Fassung“ liegen darueber und sind einzeln
 * per Tastatur erreichbar. Angaben, die der Stand nicht traegt (Kosten, Runde),
 * erscheinen nicht.
 */
const props = defineProps<{
  entry: RunEntry
  layout: 'tiles' | 'list'
  selected: boolean
  versionsOpen: boolean
  versionsState?: VersionsState
}>()
const emit = defineEmits<{ (e: 'toggle-select'): void; (e: 'toggle-versions'): void }>()

const { t, te, locale } = useI18n()

const target = computed(() => entryTarget(props.entry))

const date = computed(() => formatShelfDate(props.entry.lauf.updatedAt, locale.value, t))

const progress = computed(() => {
  if (!props.entry.running) return null
  const p = props.entry.lauf.progress
  return typeof p === 'number' ? p : null
})

const reasonText = computed(() => {
  const r = props.entry.reason
  if (!r) return ''
  switch (r.code) {
    case 'budget': {
      const specific = r.detail ? `views.library.runs.reason.${r.detail}` : ''
      return specific && te(specific) ? t(specific) : t('views.library.runs.reason.budget')
    }
    case 'user_stop':
    case 'process_restart':
    case 'incomplete':
      return t(`views.library.runs.reason.${r.code}`)
    default: {
      // Statusmeldung des Jobs; ohne sie der allgemeine Satz zum Zustand.
      const message = r.job ? jobStatusMessage(r.job, t, te) : ''
      return message || t(`views.library.runs.reason.${r.code}`)
    }
  }
})

const versionsId = computed(() => `run-versions-${props.entry.lauf.id}`)
const latestReportId = computed(() => props.entry.reports[0]?.id ?? null)
const count = computed(() => props.entry.reports.length)
</script>

<template>
  <li class="run-tile" :class="[`run-tile--${layout}`, { 'run-tile--selected': selected }]" :data-run-id="entry.lauf.id" :data-state="entry.state">
    <label class="run-tile__select">
      <input type="checkbox" :checked="selected" @change="emit('toggle-select')" />
      <span class="sr-only">{{ t('views.library.runs.tile.select', { title: entry.title }) }}</span>
    </label>

    <div class="run-tile__main">
      <h3 class="run-tile__title">
        <RouterLink v-if="target" :to="target" class="run-tile__link">{{ entry.title }}</RouterLink>
        <template v-else>{{ entry.title }}</template>
      </h3>
    </div>

    <!-- Direkt unter dem Titel: Titel-Link und diese Knöpfe sind aufeinanderfolgende
         Tab-Stops. Läge dazwischen eine hohe Kachel, scrollte der Browser beim Tab
         zum Knopf (zentriert) und die Reihenfolge sähe wie ein Sprung nach oben aus. -->
    <div v-if="count > 0" class="run-tile__reports">
      <button
        type="button"
        class="run-tile__btn"
        :aria-expanded="versionsOpen"
        :aria-controls="versionsId"
        @click="emit('toggle-versions')"
      >
        {{ t('views.library.runs.versions.count', { n: count }, count) }}
      </button>
      <RouterLink v-if="latestReportId" class="run-tile__btn" :to="reportLink(latestReportId, entry.lauf.id)">
        {{ t('views.library.runs.versions.openLatest') }}
      </RouterLink>
    </div>

    <p v-if="entry.source" class="run-tile__source">
      <span class="run-tile__source-label">{{ t('views.library.runs.tile.source') }}</span> {{ entry.source }}
    </p>

    <div class="run-tile__status">
      <RunStateMark :state="entry.state" />
      <template v-if="progress !== null">
        <span class="run-tile__progress" role="progressbar" :aria-valuenow="progress" aria-valuemin="0" aria-valuemax="100" :aria-label="t('views.library.runs.tile.progress', { n: progress })">
          <span class="run-tile__progress-fill" :style="{ width: `${progress}%` }" />
        </span>
        <span class="run-tile__progress-text">{{ t('views.library.runs.tile.progress', { n: progress }) }}</span>
      </template>
    </div>

    <p v-if="reasonText" class="run-tile__reason">{{ reasonText }}</p>

    <RunStageDots class="run-tile__stages" :stages="entry.stages" />

    <p class="run-tile__date">{{ date }}</p>

    <RunVersionsList v-if="versionsOpen && versionsState" :id="versionsId" :state="versionsState" :simulation-id="entry.lauf.id" class="run-tile__versions" />
  </li>
</template>

<style scoped>
.run-tile {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 12px;
  background: var(--s2);
  border: 1px solid transparent;
  list-style: none;
}
.run-tile:hover {
  background: var(--s3);
}
.run-tile:focus-within {
  border-color: var(--acc-text);
}
.run-tile--selected {
  border-color: var(--fg2);
}
.run-tile__select {
  position: absolute;
  top: 10px;
  right: 12px;
  z-index: 3;
  display: inline-flex;
}
.run-tile__select input {
  width: 16px;
  height: 16px;
  margin: 0;
  cursor: pointer;
}
.run-tile__select input:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}
.run-tile__main {
  min-width: 0;
  padding-right: 28px;
}
.run-tile__title {
  margin: 0;
  min-height: 2.8em;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--fg);
  overflow-wrap: anywhere;
}
.run-tile__link {
  color: inherit;
  text-decoration: none;
}
.run-tile__link::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 1;
  border-radius: 12px;
}
.run-tile__link:focus-visible {
  outline: none;
}
.run-tile__link:focus-visible::after {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}
.run-tile__source {
  margin: 0;
  font-size: 12.5px;
  color: var(--fg2);
  overflow-wrap: anywhere;
}
.run-tile__source-label {
  color: var(--fg3);
}
.run-tile__status {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.run-tile__progress {
  width: 72px;
  height: 4px;
  border-radius: 2px;
  background: var(--s4);
  overflow: hidden;
}
.run-tile__progress-fill {
  display: block;
  height: 100%;
  background: var(--fg);
}
.run-tile__progress-text {
  font-size: 12px;
  color: var(--fg2);
  font-variant-numeric: tabular-nums;
}
.run-tile__reason {
  margin: 0;
  font-size: 12.5px;
  color: var(--fg2);
  overflow-wrap: anywhere;
}
.run-tile__date {
  margin: 0;
  font-size: 12.5px;
  color: var(--fg2);
  font-variant-numeric: tabular-nums;
}
.run-tile__reports {
  position: relative;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.run-tile__btn {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 10px;
  border: none;
  border-radius: 8px;
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 12.5px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
}
.run-tile__btn:hover {
  background: var(--s4);
}
.run-tile__btn:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

/* Listenansicht: dieselben Angaben in Spalten. */
.run-tile--list {
  display: grid;
  grid-template-columns: 24px minmax(0, 3fr) auto minmax(0, 2fr) minmax(0, 3fr) 90px;
  align-items: center;
  column-gap: 16px;
  padding: 10px 16px;
}
/* Feste Zeilen: die Knöpfe stehen in der zweiten Zeile unter Grund und Stufen,
   nicht unter dem Titel. So liegen aufeinanderfolgende Tab-Stops (Titel-Link,
   Knöpfe) in verschiedenen Spalten. */
.run-tile--list .run-tile__select {
  position: static;
  grid-column: 1;
  grid-row: 1;
}
.run-tile--list .run-tile__main {
  grid-column: 2;
  grid-row: 1;
  padding-right: 0;
}
.run-tile--list .run-tile__title {
  min-height: 0;
  font-size: 14px;
}
.run-tile--list .run-tile__source {
  grid-column: 2;
  grid-row: 2;
  margin: 0;
}
.run-tile--list .run-tile__status {
  grid-column: 3;
  grid-row: 1;
}
.run-tile--list .run-tile__reason {
  grid-column: 4;
  grid-row: 1;
}
.run-tile--list .run-tile__stages {
  grid-column: 5;
  grid-row: 1;
}
.run-tile--list .run-tile__date {
  grid-column: 6;
  grid-row: 1;
  text-align: right;
}
.run-tile--list .run-tile__reports {
  grid-column: 4 / -1;
  grid-row: 2;
}
.run-tile--list .run-tile__versions {
  grid-column: 2 / -1;
  grid-row: 3;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
