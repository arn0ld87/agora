<template>
  <div class="shelf" :data-testid="ShelfTestId.root">
    <div class="shelf__head">
      <h3 class="shelf__title">{{ t('shelf.title') }}</h3>
      <p class="shelf__subtitle">{{ t('shelf.subtitle', { n: props.shelf.objects.value.length }) }}</p>
      <p v-if="props.shelf.error.value" class="shelf__error">{{ props.shelf.error.value }}</p>
    </div>

    <div class="shelf__filter" role="tablist" :aria-label="t('shelf.title')" :data-testid="ShelfTestId.filter">
      <button
        v-for="pill in filterPills"
        :key="pill.key"
        type="button"
        role="tab"
        class="shelf__filter-pill"
        :class="{ 'shelf__filter-pill--active': props.shelf.filter.value === pill.key }"
        :aria-selected="props.shelf.filter.value === pill.key"
        :data-testid="ShelfTestId.filterPill"
        @click="emit('filterChange', pill.key)"
      >
        {{ pill.label }}<span class="shelf__filter-count">{{ pill.count }}</span>
      </button>
    </div>

    <!-- Umschalter Liste ⇄ Tabelle (Redesign PR 8): nur fuer die Filter
         „lauf“/„jobs“ — die anderen Filter sind keine dichten Datensaetze. -->
    <div
      v-if="tableAllowed"
      class="shelf__view-toggle"
      role="group"
      :aria-label="t('shelf.table.toggleAria')"
      :data-testid="ShelfTableTestId.toggle"
    >
      <button
        type="button"
        class="shelf__view-toggle-btn"
        :class="{ 'shelf__view-toggle-btn--active': effectiveViewMode === 'list' }"
        :aria-pressed="effectiveViewMode === 'list'"
        :data-testid="ShelfTableTestId.toggleList"
        @click="setViewMode('list')"
      >
        {{ t('shelf.table.toggleList') }}
      </button>
      <button
        type="button"
        class="shelf__view-toggle-btn"
        :class="{ 'shelf__view-toggle-btn--active': effectiveViewMode === 'table' }"
        :aria-pressed="effectiveViewMode === 'table'"
        :data-testid="ShelfTableTestId.toggleTable"
        @click="setViewMode('table')"
      >
        {{ t('shelf.table.toggleTable') }}
      </button>
    </div>

    <div class="shelf__body">
      <!-- Tabellenmodus „lauf“ (Redesign PR 8): DataTable statt Zeilenliste. -->
      <div v-if="props.shelf.filter.value === 'lauf' && effectiveViewMode === 'table'" :data-testid="ShelfTableTestId.root">
        <DataTable :columns="laufColumns" :rows="laufTableRows" :row-click="(row) => selectRow((row as LaufTableRow).raw)" :row-selected="(row) => isSelected((row as LaufTableRow).raw)">
          <template #cell-nextAction="{ row }">
            <span class="shelf__table-actions">
              <button
                v-if="(row as LaufTableRow).raw.nextAction"
                type="button"
                class="shelf__row-btn"
                :class="nextActionClass((row as LaufTableRow).raw.nextAction!.kind)"
                :data-testid="ShelfTestId.rowNextAction"
                @click.stop="goToNextAction((row as LaufTableRow).raw)"
              >
                {{ (row as LaufTableRow).raw.nextAction!.label }}
              </button>
              <button
                v-if="(row as LaufTableRow).simulationId"
                type="button"
                class="shelf__row-btn shelf__row-btn--ghost"
                :data-testid="ShelfTableTestId.compareAction"
                @click.stop="goToCompare((row as LaufTableRow).simulationId as string)"
              >
                {{ t('shelf.table.compare') }}
              </button>
            </span>
          </template>
          <template #empty>
            <span :data-testid="ShelfTestId.empty">{{ t('shelf.empty') }}</span>
          </template>
        </DataTable>
      </div>

      <!-- Tabellenmodus „jobs“ (Redesign PR 8): dieselbe DataTable-Komponente
           wie „lauf“, statt der eigenen Mono-Tabelle unten. -->
      <div
        v-else-if="props.shelf.filter.value === 'jobs' && effectiveViewMode === 'table'"
        :data-testid="ShelfTableTestId.root"
      >
        <DataTable :columns="jobColumns" :rows="jobTableRows">
          <template #empty>
            <span :data-testid="ShelfTestId.empty">{{ t('shelf.empty') }}</span>
          </template>
        </DataTable>
      </div>

      <!-- Filter „Alle Jobs“ (Q19c), Listenmodus: schlichte Mono-Tabelle aus der Rohebene.
           `tabindex="0"` + `role="region"` + Name: der Kasten scrollt horizontal,
           und ein scrollbarer Bereich ohne Fokus ist per Tastatur nicht
           erreichbar (axe `scrollable-region-focusable`, serious). Der Befund
           lag hier schon vorher, wurde aber von keinem Gate beruehrt, solange
           keine geprüfte Route auf diesen Filter zeigte — der /v4/history-
           Redirect (PR 8) tut das jetzt. -->
      <div
        v-else-if="props.shelf.filter.value === 'jobs'"
        class="shelf__jobs-scroll"
        role="region"
        tabindex="0"
        :aria-label="t('shelf.filter.jobs')"
      >
      <table class="shelf__jobs-table" :data-testid="ShelfTestId.jobsTable">
        <thead>
          <tr>
            <th>{{ t('shelf.filter.jobs') }}</th>
            <th>{{ t('common.type') }}</th>
            <th>{{ t('common.status') }}</th>
            <th>{{ t('common.time') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="job in props.shelf.jobs.value" :key="job.runId">
            <td class="shelf__jobs-id">{{ job.runId }}</td>
            <td>{{ job.runType }}</td>
            <td>{{ job.message || statusText(t, `shelf.status.${job.status}`, job.status) }}</td>
            <td class="shelf__jobs-time">{{ formatUpdatedAt(job.updatedAt) }}</td>
          </tr>
        </tbody>
      </table>
      </div>

      <template v-else>
        <p v-if="props.shelf.loading.value && visibleRows.length === 0" class="shelf__loading">{{ t('common.loading') }}</p>
        <p v-else-if="visibleRows.length === 0" class="shelf__empty" :data-testid="ShelfTestId.empty">
          {{ t('shelf.empty') }}
        </p>

        <ul v-else class="shelf__list" role="list">
          <li
            v-for="(obj, index) in visibleRows"
            :key="`${obj.kind}:${obj.id}`"
            :ref="(el) => setRowRef(el as HTMLElement | null, index)"
            class="shelf__row"
            :class="{
              'shelf__row--selected': isSelected(obj),
              'shelf__row--active': obj.active !== null,
              'shelf__row--warn': obj.nextAction?.kind === 'warn',
            }"
            role="listitem"
            :tabindex="index === activeIndex ? 0 : -1"
            :aria-current="isSelected(obj) ? 'true' : undefined"
            :data-testid="ShelfTestId.row"
            @click="selectRow(obj)"
            @keydown="onRowKeydown($event, index)"
          >
            <span class="shelf__row-tag" :data-testid="ShelfTestId.rowTag">{{ SHELF_KIND_TAG[obj.kind] }}</span>
            <span class="shelf__row-main">
              <span class="shelf__row-title" :data-testid="ShelfTestId.rowTitle">{{ obj.title }}</span>
              <span class="shelf__row-status" :data-testid="ShelfTestId.rowStatus">{{ obj.statusLine }}</span>
              <span class="shelf__row-meta">{{ formatUpdatedAt(obj.updatedAt) }} · {{ obj.metaId }}</span>
              <span v-if="personaStartErrorId === obj.id" class="shelf__row-error" role="alert" :data-testid="ShelfTestId.rowPersonaError">
                {{ t('shelf.dossier.startFailed') }}
              </span>
            </span>
            <span class="shelf__row-actions">
              <button
                v-if="obj.active"
                type="button"
                class="shelf__row-btn shelf__row-btn--ghost"
                :data-testid="ShelfTestId.rowCancel"
                :tabindex="index === activeIndex ? 0 : -1"
                @click.stop="cancelAction.cancel(obj.active.runId)"
              >
                {{ t('shelf.cancel') }}
              </button>
              <button
                v-if="obj.active?.pausable && obj.active.simulationId"
                type="button"
                class="shelf__row-btn shelf__row-btn--ghost"
                :data-testid="ShelfTestId.rowPause"
                :tabindex="index === activeIndex ? 0 : -1"
                @click.stop="togglePause(obj.active)"
              >
                {{ obj.active.status === 'paused' ? t('shelf.resume') : t('shelf.pause') }}
              </button>
              <button
                v-if="obj.nextAction"
                type="button"
                class="shelf__row-btn"
                :class="nextActionClass(obj.nextAction.kind)"
                :data-testid="ShelfTestId.rowNextAction"
                :tabindex="index === activeIndex ? 0 : -1"
                @click.stop="goToNextAction(obj)"
              >
                {{ obj.nextAction.label }}
              </button>
              <!-- Personasatz hat keine routbare Weiter-Aktion (kein
                   Projekt/keine Simulation existiert vor dem Start) —
                   die Zeile startet den Lauf direkt (Block B4, geteilt
                   mit Dossier.vue ueber useStartFromPersona). -->
              <button
                v-else-if="obj.kind === 'personasatz'"
                type="button"
                class="shelf__row-btn shelf__row-btn--accent"
                :data-testid="ShelfTestId.rowNextAction"
                :disabled="startFromPersonaAction.busy.value"
                :tabindex="index === activeIndex ? 0 : -1"
                @click.stop="startPersonaRun(obj)"
              >
                {{ t('shelf.dossier.startFromPersona') }}
              </button>
            </span>
          </li>
        </ul>
      </template>

      <div class="shelf__new-object">
        <button type="button" class="shelf__new-object-btn" :data-testid="ShelfTestId.newObject" @click="goToNewObject">
          {{ t('shelf.newObject') }}
        </button>
        <span class="shelf__new-object-hint">{{ t('shelf.newObjectHint') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import DataTable, { type DataTableColumn } from '../v4/data/DataTable.vue'
import { ShelfTableTestId, ShelfTestId } from '../../contracts/testIds'
import { SHELF_KIND_TAG, type ShelfFilter, type ShelfObject } from '../../types/shelf'
import { formatShelfDate, statusText, type useShelf } from '../../composables/useShelf'
import { useCancelAction } from './useCancelAction'
import { useStartFromPersona } from '../../composables/useStartFromPersona'

/**
 * Shelf.vue — die Ablage-Liste (Block B3).
 *
 * Bekommt die Datenschicht (useShelf-Rueckgabe) als Prop von ShelfView,
 * NICHT als eigener useShelf()-Aufruf: useShelf() erzeugt bei jedem
 * Aufruf frische Refs, waere hier also ein zweiter, unabhaengiger
 * Zustand statt desselben, den ShelfView pollt.
 *
 * Filterwechsel laeuft ueber ein Event (filterChange) statt direkter
 * Mutation von props.shelf.filter.value — vue/no-mutating-props laesst
 * sich zwar mit derselben Ref-Identitaet technisch umgehen, aber die
 * saubere Props-runter/Events-hoch-Richtung bleibt bei ShelfView, wo
 * `shelf` kein Prop, sondern der lokale useShelf()-Aufruf ist.
 *
 * A11y (09-systemregeln.html): die Liste ist EINE role="list"; Tab
 * springt nicht durch alle Zeilen — roving tabindex (activeIndex) haelt
 * genau eine Zeile (und ihre Aktions-Buttons) im normalen Tab-Fluss,
 * Pfeiltasten wandern zwischen den Zeilen.
 */

const props = defineProps<{
  shelf: ReturnType<typeof useShelf>
  selected: ShelfObject | null
}>()

const emit = defineEmits<{ select: [obj: ShelfObject]; filterChange: [filter: ShelfFilter] }>()

const { t, locale } = useI18n()
const router = useRouter()
const cancelAction = useCancelAction()
const startFromPersonaAction = useStartFromPersona()
const personaStartErrorId = ref<string | null>(null)

const FILTER_ORDER: ShelfFilter[] = ['alle', 'lauf', 'bericht', 'personasatz', 'graph', 'jobs']

const filterPills = computed(() =>
  FILTER_ORDER.map((key) => ({
    key,
    label: t(`shelf.filter.${key}`),
    count: key === 'jobs' ? props.shelf.jobs.value.length : props.shelf.counts.value[key],
  })),
)

const visibleRows = computed(() => props.shelf.filtered.value)

// ── Tabellenmodus (Redesign PR 8, Audit §7 "Läufe (/runs)") ──────────
//
// Umschalter Liste ⇄ Tabelle. Nur die Filter „lauf" und „jobs" bieten den
// Tabellenmodus an — die anderen Filter (Berichte/Personas/Graphen) sind
// keine dichten, spaltenartigen Datensaetze; der Umschalter verschwindet
// dort ganz statt deaktiviert dazustehen (weniger UI-Rauschen als ein
// Knopf, der ohnehin nie greift). Die Wahl wird pro Benutzer gemerkt.
const VIEW_MODE_STORAGE_KEY = 'agora.shelf.viewMode'
type ShelfViewMode = 'list' | 'table'

function loadViewMode(): ShelfViewMode {
  try {
    return localStorage.getItem(VIEW_MODE_STORAGE_KEY) === 'table' ? 'table' : 'list'
  } catch {
    return 'list'
  }
}

const viewMode = ref<ShelfViewMode>(loadViewMode())

function setViewMode(mode: ShelfViewMode): void {
  viewMode.value = mode
  try {
    localStorage.setItem(VIEW_MODE_STORAGE_KEY, mode)
  } catch {
    // localStorage kann in privaten Tabs/über Quota fehlschlagen — die Wahl
    // gilt dann nur fuer diese Sitzung, die Ablage bleibt bedienbar.
  }
}

const tableAllowed = computed(() => props.shelf.filter.value === 'lauf' || props.shelf.filter.value === 'jobs')
const effectiveViewMode = computed<ShelfViewMode>(() => (tableAllowed.value ? viewMode.value : 'list'))

/**
 * Aussagen/Belege/Lücken sind bewusst KEINE Spalten dieser Tabelle (Audit
 * Zeile 137 nennt sie als Sollzustand). Sie kommen aus
 * getReportEvidence(reportId) (useObjectDetail.ts) — ein Fetch PRO BERICHT.
 * Eine Läufe-Tabelle mit N Zeilen bräuchte N Evidence-Fetches; die ganze
 * Redesign-Serie kommt ohne neue Backend-Endpunkte aus, und ein N+1 im
 * Listen-Pfad ist keine Option. Die drei Kennzahlen bleiben im
 * Kennzahlstreifen des Dossiers (Redesign PR 4).
 *
 * „Vergleichen" ersetzt die im Audit vorgesehene Zwei-Läufe-Auswahl:
 * CompareView.vue (Route CompareV4, /v4/compare/:simulationId) vergleicht
 * BRANCHES EINER Simulation über listSimulationBranches(simulationId) —
 * nicht zwei beliebige Läufe. Eine Mehrfachauswahl aus dieser Tabelle hätte
 * keinen Endpunkt, der sie einlöst. Stattdessen: eine Zeilenaktion
 * „Vergleichen" pro Lauf, die zu CompareV4 führt, wenn eine simulationId
 * ermittelbar ist — keine erfundene Compare-API.
 */
interface LaufTableRow extends Record<string, unknown> {
  id: string
  title: string
  statusLine: string
  progress: number | null
  personaCount: number | null
  updatedAt: string
  simulationId: string | null
  raw: ShelfObject
}

function simulationIdForLauf(obj: ShelfObject): string | null {
  if (obj.active?.simulationId) return obj.active.simulationId
  for (const job of obj.jobs ?? []) {
    const sid = job.linkedIds?.simulation_id
    if (typeof sid === 'string' && sid) return sid
  }
  return null
}

const laufColumns = computed<DataTableColumn[]>(() => [
  { key: 'title', label: t('shelf.table.colTitle') },
  { key: 'statusLine', label: t('shelf.table.colStatus') },
  { key: 'progress', label: t('shelf.table.colProgress'), align: 'right', mono: true, width: '90px' },
  { key: 'personaCount', label: t('shelf.table.colPersonas'), align: 'right', mono: true, width: '90px' },
  { key: 'updatedAt', label: t('shelf.table.colUpdatedAt'), mono: true, width: '120px' },
  { key: 'nextAction', label: t('shelf.table.colNextAction') },
])

const laufTableRows = computed<LaufTableRow[]>(() =>
  visibleRows.value.map((obj) => ({
    id: `${obj.kind}:${obj.id}`,
    title: obj.title,
    statusLine: obj.statusLine,
    progress: obj.progress ?? obj.active?.progress ?? null,
    personaCount: obj.personaCount ?? null,
    updatedAt: formatUpdatedAt(obj.updatedAt),
    simulationId: simulationIdForLauf(obj),
    raw: obj,
  })),
)

interface JobTableRow extends Record<string, unknown> {
  id: string
  runType: string
  status: string
  message: string
  progress: number
  updatedAt: string
}

const jobColumns = computed<DataTableColumn[]>(() => [
  { key: 'runType', label: t('shelf.table.colType') },
  { key: 'status', label: t('shelf.table.colStatus') },
  { key: 'message', label: t('shelf.table.colMessage'), secondary: true },
  { key: 'progress', label: t('shelf.table.colProgress'), align: 'right', mono: true, width: '90px' },
  { key: 'updatedAt', label: t('shelf.table.colUpdatedAt'), mono: true, width: '120px' },
])

const jobTableRows = computed<JobTableRow[]>(() =>
  props.shelf.jobs.value.map((job) => ({
    id: job.runId,
    runType: job.runType,
    status: statusText(t, `shelf.status.${job.status}`, job.status),
    message: job.message,
    progress: job.progress,
    updatedAt: formatUpdatedAt(job.updatedAt),
  })),
)

function goToCompare(simulationId: string): void {
  void router.push({ name: 'CompareV4', params: { simulationId } })
}

function isSelected(obj: ShelfObject): boolean {
  return props.selected !== null && props.selected.kind === obj.kind && props.selected.id === obj.id
}

function selectRow(obj: ShelfObject): void {
  emit('select', obj)
}

function goToNextAction(obj: ShelfObject): void {
  if (!obj.nextAction) return
  void router.push(obj.nextAction.to)
}

function goToNewObject(): void {
  void router.push({ name: 'Dashboard' })
}

function nextActionClass(kind: 'accent' | 'warn' | 'neutral'): string {
  return `shelf__row-btn--${kind}`
}

function togglePause(active: NonNullable<ShelfObject['active']>): void {
  if (!active.simulationId) return
  if (active.status === 'paused') void cancelAction.resume(active.simulationId)
  else void cancelAction.pause(active.simulationId)
}

async function startPersonaRun(obj: ShelfObject): Promise<void> {
  personaStartErrorId.value = null
  const res = await startFromPersonaAction.start(obj.id, t('shelf.dossier.startName', { title: obj.title }))
  if (res) void router.push({ name: 'StepEnvSetup', params: { projectId: res.simulationId } })
  else personaStartErrorId.value = obj.id
}

function formatUpdatedAt(iso: string): string {
  return formatShelfDate(iso, locale.value, t)
}

// ── Roving tabindex ─────────────────────────────────────────────
const activeIndex = ref(0)
const rowRefs = ref<(HTMLElement | null)[]>([])

function setRowRef(el: HTMLElement | null, index: number): void {
  rowRefs.value[index] = el
}

watch(visibleRows, (rows) => {
  if (activeIndex.value >= rows.length) activeIndex.value = Math.max(0, rows.length - 1)
})

function moveTo(index: number): void {
  const rows = visibleRows.value
  if (rows.length === 0) return
  const clamped = Math.max(0, Math.min(rows.length - 1, index))
  activeIndex.value = clamped
  void nextTick(() => rowRefs.value[clamped]?.focus())
}

function onRowKeydown(e: KeyboardEvent, index: number): void {
  switch (e.key) {
    case 'ArrowDown':
      e.preventDefault()
      moveTo(index + 1)
      break
    case 'ArrowUp':
      e.preventDefault()
      moveTo(index - 1)
      break
    case 'Home':
      e.preventDefault()
      moveTo(0)
      break
    case 'End':
      e.preventDefault()
      moveTo(visibleRows.value.length - 1)
      break
    case 'Enter':
    case ' ':
      e.preventDefault()
      selectRow(visibleRows.value[index])
      break
    default:
      break
  }
}
</script>

<style scoped>
.shelf {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

.shelf__head {
  padding: var(--sp-5) var(--sp-5) var(--sp-3);
}

.shelf__title {
  margin: 0 0 3px;
  font-family: var(--font-sans);
  font-size: var(--fs-title-3);
  font-weight: 600;
  letter-spacing: var(--tr-title-3);
  color: var(--text-primary);
}

.shelf__subtitle {
  margin: 0;
  font-size: var(--fs-caption-1);
  color: var(--text-secondary);
}

.shelf__error {
  margin: 6px 0 0;
  font-size: var(--fs-caption-1);
  color: var(--status-orange);
}

.shelf__filter {
  display: flex;
  gap: 14px;
  padding: 0 var(--sp-5) var(--sp-2);
  flex-wrap: wrap;
}

.shelf__filter-pill {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  border: 0;
  border-bottom: 1.5px solid transparent;
  background: transparent;
  color: var(--text-tertiary);
  font-family: var(--font-sans);
  font-size: var(--fs-caption-1);
  padding-bottom: 4px;
  cursor: pointer;
}

.shelf__filter-pill--active {
  color: var(--text-primary);
  border-bottom-color: var(--accent);
}

.shelf__filter-pill:hover:not(.shelf__filter-pill--active) {
  color: var(--text-secondary);
}

.shelf__filter-pill:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.shelf__filter-count {
  font-family: var(--font-mono);
  color: var(--text-tertiary);
}

.shelf__filter-pill--active .shelf__filter-count {
  color: var(--text-secondary);
}

.shelf__view-toggle {
  display: inline-flex;
  gap: 2px;
  margin: 0 var(--sp-5) var(--sp-2);
  padding: 2px;
  border: 1px solid var(--hairline);
  border-radius: var(--r-3);
  width: fit-content;
}

.shelf__view-toggle-btn {
  border: 0;
  background: transparent;
  border-radius: var(--r-2);
  padding: 3px 10px;
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 500;
  color: var(--text-tertiary);
  cursor: pointer;
}

.shelf__view-toggle-btn--active {
  background: var(--surface-hover);
  color: var(--text-primary);
}

.shelf__view-toggle-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.shelf__table-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.shelf__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--hairline);
}

.shelf__loading,
.shelf__empty {
  padding: var(--sp-5);
  font-size: var(--fs-callout);
  color: var(--text-secondary);
}

.shelf__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.shelf__row {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  align-items: start;
  gap: 11px;
  border-top: 1px solid var(--hairline);
  border-left: 2px solid transparent;
  padding: 13px var(--sp-5) 13px 18px;
  cursor: pointer;
}

.shelf__list > .shelf__row:first-child {
  border-top: 1px solid var(--hairline);
}

.shelf__row:hover {
  background: var(--surface-hover);
}

.shelf__row--selected {
  background: var(--accent-tint-bg);
  border-left-color: var(--accent);
}

.shelf__row--active:not(.shelf__row--selected) {
  background: var(--status-teal-bg);
}

.shelf__row--warn:not(.shelf__row--selected) {
  border-left-color: var(--status-orange);
}

.shelf__row:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.shelf__row-tag {
  font-family: var(--font-mono);
  font-size: 9.5px;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
  border: 1px solid var(--hairline-strong);
  border-radius: 2px;
  height: 17px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.shelf__row--active .shelf__row-tag {
  color: var(--status-teal);
  border-color: var(--status-teal);
}

.shelf__row--warn .shelf__row-tag {
  color: var(--status-orange);
  border-color: var(--status-orange);
}

.shelf__row-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.shelf__row-title {
  font-size: var(--fs-callout);
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-primary);
}

.shelf__row-status {
  font-size: var(--fs-caption-1);
  color: var(--text-secondary);
  margin-top: 2px;
}

.shelf__row--active .shelf__row-status {
  color: var(--status-teal);
}

.shelf__row-meta {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-tertiary);
  margin-top: 3px;
}

.shelf__row-error {
  display: block;
  margin-top: 3px;
  font-size: var(--fs-caption-1);
  color: var(--status-red);
}

.shelf__row-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.shelf__row-btn {
  height: 26px;
  padding: 0 10px;
  border-radius: var(--r-3);
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
}

.shelf__row-btn--ghost {
  background: transparent;
  border: 1px solid var(--hairline);
  color: var(--text-secondary);
}

.shelf__row-btn--ghost:hover {
  color: var(--text-primary);
  border-color: var(--hairline-strong);
}

.shelf__row-btn--accent {
  background: transparent;
  border: 1px solid var(--accent);
  color: var(--accent);
}

.shelf__row-btn--accent:hover {
  background: var(--accent-tint-bg);
}

.shelf__row-btn--warn {
  background: transparent;
  border: 1px solid var(--status-orange);
  color: var(--status-orange);
}

.shelf__row-btn--warn:hover {
  background: var(--status-orange-bg);
}

.shelf__row-btn--neutral {
  background: transparent;
  border: 1px solid var(--hairline);
  color: var(--text-tertiary);
}

.shelf__row-btn--neutral:hover {
  color: var(--text-secondary);
  border-color: var(--hairline-strong);
}

.shelf__row-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* Die Rohebene ist breiter als ein Telefon. Sie scrollt in ihrem
   eigenen Kasten — das Dokument selbst darf nie horizontal scrollen
   (harte Vorgabe des Accessibility-Gates bei 320px). */
.shelf__jobs-scroll {
  overflow-x: auto;
  max-width: 100%;
}

/* Der Kasten ist fokussierbar (siehe Template) und braucht deshalb einen
   sichtbaren Ring. Bewusst ohne `transition` — der Playwright-Fokuscheck misst
   nach einem einzigen requestAnimationFrame. */
.shelf__jobs-scroll:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.shelf__jobs-table {
  width: 100%;
  min-width: 480px;
  border-collapse: collapse;
  font-family: var(--font-mono);
  font-size: 11px;
}

.shelf__jobs-table th,
.shelf__jobs-table td {
  text-align: left;
  padding: 8px var(--sp-5);
  border-top: 1px solid var(--hairline);
  color: var(--text-secondary);
}

.shelf__jobs-table th {
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: 9.5px;
  border-top: none;
  border-bottom: 1px solid var(--hairline);
}

.shelf__jobs-id,
.shelf__jobs-time {
  color: var(--text-primary);
}

.shelf__new-object {
  margin-top: auto;
  border-top: 1px solid var(--hairline);
  padding: 14px var(--sp-5);
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.shelf__new-object-btn {
  height: 30px;
  padding: 0 12px;
  background: var(--accent);
  border: 0;
  border-radius: var(--r-3);
  color: var(--text-on-accent);
  font-family: var(--font-sans);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}

.shelf__new-object-btn:hover {
  background: var(--accent-hover);
}

.shelf__new-object-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.shelf__new-object-hint {
  font-size: var(--fs-caption-1);
  color: var(--text-tertiary);
}

@media (prefers-reduced-motion: reduce) {
  .shelf__row,
  .shelf__row-btn,
  .shelf__filter-pill {
    transition: none;
  }
}
</style>
