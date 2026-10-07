<script setup lang="ts">
/**
 * Stufentabelle der Übersicht (Bauplan 4.2): eine Zeile je Stufe mit Zustand,
 * Modell, Dauer, Tokens, Kosten und genau einem Knopf "Nächster Schritt".
 * Was die Daten nicht tragen, steht als "nicht erfasst", nie als 0.
 */
import { useI18n } from 'vue-i18n'
import RunStateMark from './RunStateMark.vue'
import RunReportRegenerate from './RunReportRegenerate.vue'
import { wallClockSeconds, type StageKey, type StageRow } from '@/composables/run/runStageState'
import { formatCostMicros, formatDuration, formatTokens } from '@/utils/format'

const props = defineProps<{
  rows: StageRow[]
  hasReport: boolean
  /** Workspace-Standardmodell je Stufe (nur Anzeige, keine Zusage für diesen Lauf). */
  defaultModels?: Partial<Record<StageKey, string | null>>
  simulationId?: string
}>()
const emit = defineEmits<{ reload: [] }>()
const { t, te, locale } = useI18n()

const ACTIVE = new Set(['running', 'queued', 'paused'])

/** Nur mit vorhandenem Bericht und ohne aktiven Berichtsjob; nie für Graph, Personas, Simulation. */
function canRegenerate(row: StageRow): boolean {
  return row.key === 'report' && !!row.reportId && !!props.simulationId && !ACTIVE.has(row.state)
}

type ModelCell =
  | { kind: 'run'; route: { model: string; providerId: string } }
  | { kind: 'ledger'; models: string[] }
  | { kind: 'default'; model: string | null }
  | { kind: 'missing' }

function modelCell(row: StageRow): ModelCell {
  if (row.key === 'interviews') return { kind: 'missing' }
  const job = row.job
  if (job) {
    if (job.route) return { kind: 'run', route: job.route }
    return job.models.length ? { kind: 'ledger', models: job.models } : { kind: 'missing' }
  }
  if (row.state === 'notStarted') return { kind: 'default', model: props.defaultModels?.[row.key] ?? null }
  return { kind: 'missing' }
}

/** Modell am Startknopf: Standard vor dem Start, bei Fortsetzung die gelaufene Route. */
function stepModel(row: StageRow): string | null {
  if (!row.next.to) return null
  if (row.next.kind === 'start') return props.defaultModels?.[row.key] ?? null
  if (row.next.kind === 'resume') return row.job?.route?.model ?? null
  return null
}
function stepLabel(row: StageRow): string {
  const step = t(`views.run.step.${row.next.kind}`)
  const m = stepModel(row)
  return m ? t('views.run.overview.stepWithModel', { step, model: m }) : step
}

function notes(row: StageRow): string[] {
  const out: string[] = []
  for (const d of row.degradations) {
    const key = `views.run.degradation.${d.code}`
    const label = te(key) ? t(key, { count: d.count ?? 0 }) : ''
    out.push([label, d.detail].filter(Boolean).join(': '))
  }
  if (row.terminationReason && ['stopped', 'failed', 'budget'].includes(row.state)) {
    const key = `views.run.termination.${row.terminationReason}`
    out.push(te(key) ? t(key) : row.terminationReason)
  }
  if (row.state === 'failed' && row.job?.error) out.push(row.job.error)
  if (row.key === 'personas' && row.state === 'done' && !props.hasReport) {
    out.push(t('views.run.overview.fallbackUnknown'))
  }
  return out
}

function duration(row: StageRow): string | null {
  const s = row.job ? wallClockSeconds(row.job) : null
  return s === null ? null : formatDuration(s)
}
function tokens(row: StageRow): string | null {
  const n = row.job?.usage?.tokens
  return typeof n === 'number' ? formatTokens(n, locale.value) : null
}
function cost(row: StageRow): string | null {
  const n = row.job?.usage?.costMicros
  return typeof n === 'number' ? formatCostMicros(n, 'USD', locale.value) : null
}
</script>

<template>
  <!-- Schmale Fenster scrollen die Tabelle im Rahmen, nicht die Seite. Die
       Links der Spalte „Nächster Schritt“ machen den Bereich per Tastatur
       scrollbar. -->
  <div class="stage-table-wrap">
  <table class="stage-table" data-testid="run-stage-table">
    <caption class="stage-table__caption">{{ t('views.run.overview.stagesLabel') }}</caption>
    <thead>
      <tr>
        <th scope="col">{{ t('views.run.overview.col.stage') }}</th>
        <th scope="col">{{ t('views.run.overview.col.state') }}</th>
        <th scope="col">{{ t('views.run.overview.col.model') }}</th>
        <th scope="col" class="stage-table__num">{{ t('views.run.overview.col.duration') }}</th>
        <th scope="col" class="stage-table__num">{{ t('views.run.overview.col.tokens') }}</th>
        <th scope="col" class="stage-table__num">{{ t('views.run.overview.col.cost') }}</th>
        <th scope="col">{{ t('views.run.overview.col.next') }}</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="row in rows" :key="row.key" :data-testid="`stage-row-${row.key}`">
        <th scope="row" class="stage-table__stage">
          <span class="stage-table__name">{{ t(`views.run.stage.${row.key}`) }}</span>
          <ul v-if="notes(row).length" class="stage-table__notes" :data-testid="`stage-notes-${row.key}`">
            <li v-for="(n, i) in notes(row)" :key="i">{{ n }}</li>
          </ul>
        </th>
        <td><RunStateMark :state="row.state" /></td>
        <td class="stage-table__model" :data-testid="`stage-model-${row.key}`">
          <template v-for="cell in [modelCell(row)]" :key="cell.kind">
            <template v-if="cell.kind === 'run'">
              <span>{{ cell.route.model }}</span>
              <span class="stage-table__provider">{{ cell.route.providerId }}</span>
            </template>
            <template v-else-if="cell.kind === 'ledger'">{{ cell.models.join(', ') }}</template>
            <span
              v-else-if="cell.kind === 'default'"
              class="stage-table__default"
              :data-testid="`stage-model-default-${row.key}`"
              :title="t('views.run.overview.modelDefaultHint')"
            >
              <template v-if="cell.model">{{ t('views.run.overview.modelDefault', { model: cell.model }) }}</template>
              <template v-else>{{ t('views.run.overview.modelNone') }}</template>
              <span class="sr-only"> ({{ t('views.run.overview.modelDefaultHint') }})</span>
            </span>
            <span v-else class="stage-table__missing">{{ t('views.run.overview.notRecorded') }}</span>
          </template>
          <span
            v-if="row.job?.routeLoadFailed"
            class="stage-table__model-error"
            role="status"
            :data-testid="`stage-model-error-${row.key}`"
          >{{ t('views.run.overview.modelLoadFailed') }}</span>
        </td>
        <td class="stage-table__num">
          <template v-if="duration(row)">{{ duration(row) }}</template>
          <span v-else class="stage-table__missing" :title="t('views.run.overview.notRecorded')">—<span class="sr-only">{{ t('views.run.overview.notRecorded') }}</span></span>
        </td>
        <td class="stage-table__num">
          <template v-if="tokens(row)">{{ tokens(row) }}</template>
          <span v-else class="stage-table__missing" :title="t('views.run.overview.notRecorded')">—<span class="sr-only">{{ t('views.run.overview.notRecorded') }}</span></span>
        </td>
        <td class="stage-table__num">
          <template v-if="cost(row)">{{ cost(row) }}</template>
          <span v-else class="stage-table__missing" :title="t('views.run.overview.notRecorded')">—<span class="sr-only">{{ t('views.run.overview.notRecorded') }}</span></span>
        </td>
        <td>
          <router-link
            v-if="row.next.to"
            :to="row.next.to"
            class="stage-table__step"
            :class="{ 'stage-table__step--primary': row.next.kind !== 'view' }"
            :aria-label="stepLabel(row)"
            :data-testid="`stage-next-${row.key}`"
            :data-step="row.next.kind"
          >
            {{ t(`views.run.step.${row.next.kind}`) }}
            <span v-if="stepModel(row)" class="stage-table__with" aria-hidden="true">
              {{ t('views.run.overview.withModel', { model: stepModel(row) }) }}
            </span>
          </router-link>
          <template v-else>
            <button
              type="button"
              class="stage-table__step stage-table__step--disabled"
              aria-disabled="true"
              :aria-describedby="`stage-reason-${row.key}`"
              :data-testid="`stage-next-${row.key}`"
              :data-step="row.next.kind"
            >
              {{ t(`views.run.step.${row.next.kind}`) }}
            </button>
            <span :id="`stage-reason-${row.key}`" class="stage-table__reason">
              {{ t(`views.run.disabled.${row.next.disabledReason}`) }}
            </span>
          </template>
          <RunReportRegenerate
            v-if="canRegenerate(row) && simulationId"
            :simulation-id="simulationId"
            @done="emit('reload')"
          />
        </td>
      </tr>
    </tbody>
  </table>
  </div>
</template>

<style scoped>
.stage-table-wrap {
  /* Containing Block für die absolut gesetzten `.sr-only`-Texte in den Zellen:
     sonst läge ihr Bezug außerhalb des Rahmens und sie dehnten die Seite. */
  position: relative;
  max-width: 100%;
  overflow-x: auto;
  border-radius: var(--ag-r-12);
  background: var(--s2);
}
.stage-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--s2);
  border-radius: var(--ag-r-12);
  overflow: hidden;
  font-size: 13.5px;
  color: var(--fg);
}
.stage-table__caption {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
.stage-table th,
.stage-table td {
  padding: 14px 16px;
  text-align: left;
  vertical-align: top;
  border-top: 1px solid var(--line);
}
.stage-table thead th {
  border-top: none;
  font-size: 12px;
  font-weight: 600;
  color: var(--fg3);
}
.stage-table__num {
  text-align: right !important;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.stage-table__name {
  font-weight: 600;
}
.stage-table__notes {
  list-style: none;
  margin: 4px 0 0;
  padding: 0;
  font-size: 12.5px;
  font-weight: 400;
  line-height: 1.4;
  color: var(--fg2);
}
.stage-table__model {
  font-family: var(--ag-font-mono);
  font-size: 12.5px;
  color: var(--fg2);
  overflow-wrap: anywhere;
}
.stage-table__provider,
.stage-table__model-error {
  display: block;
  font-family: var(--ag-font-sans);
  font-size: 12px;
  color: var(--fg3);
}
.stage-table__default {
  font-family: var(--ag-font-sans);
  font-size: 12.5px;
  color: var(--fg3);
  font-style: italic;
}
.stage-table__with {
  display: block;
  font-size: 11.5px;
  font-weight: 400;
}
.stage-table__missing {
  font-family: var(--ag-font-sans);
  font-size: 12.5px;
  color: var(--fg3);
}
.stage-table__step {
  display: inline-flex;
  flex-direction: column;
  justify-content: center;
  min-height: 32px;
  padding: 0 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
}
.stage-table__step--primary {
  background: var(--acc);
  border-color: var(--acc);
  color: var(--on-acc);
}
.stage-table__step:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.stage-table__step--disabled {
  color: var(--fg3);
  cursor: not-allowed;
}
.stage-table__reason {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--fg3);
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
