<script setup lang="ts">
/**
 * Tabelle der Jobs der RunRegistry (Aktivität, #1797). Reine Darstellung:
 * Daten, Filter und Abbruch liegen in der Ansicht.
 *
 * Bedienung per Tastatur: Der Job-Link in der ersten Spalte öffnet die
 * Detailansicht, „Zum Lauf" und „Abbrechen" sind echte Knöpfe bzw. Links. Der
 * Klick auf die Zeile ist nur eine Abkürzung für die Maus. Die DOM-Reihenfolge
 * ist die Sichtreihenfolge.
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { formatDuration, JOB_STATE_GLYPH, type JobRow } from '@/composables/activity/jobState'

defineProps<{ rows: readonly JobRow[] }>()
const emit = defineEmits<{ cancel: [runId: string] }>()

const { t, te, locale } = useI18n()
const router = useRouter()

/** Job, für den die Rückfrage zum Abbrechen offen ist. */
const confirming = ref<string | null>(null)

function kindLabel(runType: string): string {
  return te(`views.activity.jobs.kind.${runType}`) ? t(`views.activity.jobs.kind.${runType}`) : runType
}

function reasonLabel(reason: string | null): string {
  if (!reason || !te(`views.activity.jobs.reason.${reason}`)) return ''
  return t(`views.activity.jobs.reason.${reason}`)
}

function startedLabel(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString(locale.value, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function openJob(runId: string, e: MouseEvent): void {
  const target = e.target as HTMLElement | null
  if (target?.closest('a, button')) return
  void router.push({ name: 'ActivityJobDetail', params: { runId } })
}

function confirmCancel(runId: string): void {
  confirming.value = null
  emit('cancel', runId)
}
</script>

<template>
  <div class="jobs-table-wrap">
    <table class="jobs-table">
      <caption class="sr-only">{{ t('views.activity.jobs.caption') }}</caption>
      <thead>
        <tr>
          <th scope="col">{{ t('views.activity.jobs.col.kind') }}</th>
          <th scope="col">{{ t('views.activity.jobs.col.run') }}</th>
          <th scope="col">{{ t('views.activity.jobs.col.state') }}</th>
          <th scope="col">{{ t('views.activity.jobs.col.progress') }}</th>
          <th scope="col">{{ t('views.activity.jobs.col.started') }}</th>
          <th scope="col" class="num">{{ t('views.activity.jobs.col.duration') }}</th>
          <th scope="col">{{ t('views.activity.jobs.col.actions') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="row.runId"
          class="job-row"
          :data-run-id="row.runId"
          @click="openJob(row.runId, $event)"
        >
          <th scope="row" class="kind">
            <router-link
              class="job-link"
              :to="{ name: 'ActivityJobDetail', params: { runId: row.runId } }"
              :aria-label="t('views.activity.jobs.open', { id: row.runId })"
            >{{ kindLabel(row.runType) }}</router-link>
          </th>
          <td class="run">
            <span class="run-label">{{ row.runLabel ?? row.simulationId ?? t('views.activity.jobs.unknownRun') }}</span>
            <span class="mono">{{ row.runId }}</span>
          </td>
          <td>
            <span class="badge" :class="`is-${row.state}`" data-test="state">
              <span class="glyph" aria-hidden="true">{{ JOB_STATE_GLYPH[row.state] }}</span>{{ t(`views.activity.jobs.state.${row.state}`) }}
            </span>
            <span v-if="reasonLabel(row.reason) && row.state !== 'completed'" class="reason">{{ reasonLabel(row.reason) }}</span>
          </td>
          <td class="progress-cell">
            <span class="pct">{{ row.progress }} %</span>
            <span v-if="row.state === 'running'" class="bar" aria-hidden="true"><span class="bar-fill" :style="{ width: row.progress + '%' }"></span></span>
            <span v-if="row.message" class="message">{{ row.message }}</span>
          </td>
          <td class="num-soft">{{ startedLabel(row.startedAt) }}</td>
          <td class="num num-soft">{{ formatDuration(row.durationMs) }}</td>
          <td class="actions">
            <router-link
              v-if="row.simulationId"
              class="btn"
              data-test="to-run"
              :to="{ name: 'RunOverview', params: { simulationId: row.simulationId } }"
            >{{ t('views.activity.jobs.action.toRun') }}</router-link>
            <template v-if="row.cancellable">
              <button
                v-if="confirming !== row.runId"
                type="button"
                class="btn"
                data-test="cancel"
                @click="confirming = row.runId"
              >{{ t('views.activity.jobs.action.cancel') }}</button>
              <span v-else class="confirm" role="group" :aria-label="t('views.activity.jobs.action.cancelConfirm')">
                <span class="confirm-text">{{ t('views.activity.jobs.action.cancelConfirm') }}</span>
                <button type="button" class="btn is-danger" data-test="cancel-yes" @click="confirmCancel(row.runId)">{{ t('views.activity.jobs.action.cancelYes') }}</button>
                <button type="button" class="btn" data-test="cancel-no" @click="confirming = null">{{ t('views.activity.jobs.action.cancelNo') }}</button>
              </span>
            </template>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.jobs-table-wrap { background: var(--s2); border-radius: var(--ag-r-12); overflow: auto; min-height: 0; }
.jobs-table { width: 100%; border-collapse: collapse; font-size: 13.5px; color: var(--fg); }
.jobs-table th, .jobs-table td { padding: 12px 16px; text-align: left; vertical-align: middle; }
.jobs-table thead th { font-size: 12px; font-weight: 600; color: var(--fg2); padding-top: 10px; padding-bottom: 10px; }
.job-row { border-top: 1px solid var(--line); cursor: pointer; }
.job-row:hover { background: var(--s3); }
.kind { font-weight: 600; }
.job-link { color: var(--fg); text-decoration: none; }
.job-link:hover { text-decoration: underline; }
.job-link:focus-visible, .btn:focus-visible { outline: 2px solid var(--acc); outline-offset: 2px; border-radius: var(--ag-r-6); }
.num { text-align: right !important; }
.num-soft { color: var(--fg2); font-variant-numeric: tabular-nums; white-space: nowrap; }
.run { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.run-label { font-weight: 500; }
.mono { font-family: var(--ag-font-mono); font-size: 11.5px; color: var(--fg2); }
.badge {
  display: inline-flex; align-items: center; gap: 6px; height: 24px; padding: 0 10px 0 8px;
  border-radius: var(--ag-r-pill); font-size: 12px; font-weight: 600; white-space: nowrap;
  background: var(--s3); color: var(--fg);
}
.glyph { font-size: 10.5px; line-height: 1; }
.badge.is-completed { background: var(--ok-soft); color: var(--ok); }
.badge.is-budget, .badge.is-paused { background: var(--warn-soft); color: var(--warn); }
.badge.is-failed { background: var(--err-soft); color: var(--err); }
.badge.is-pending, .badge.is-stopped { color: var(--fg2); }
.reason { display: block; margin-top: 4px; font-size: 12px; color: var(--fg2); }
.progress-cell { font-variant-numeric: tabular-nums; color: var(--fg2); min-width: 150px; }
.pct { display: block; }
.bar { display: block; height: 4px; margin-top: 5px; border-radius: 2px; background: var(--s4); overflow: hidden; }
.bar-fill { display: block; height: 100%; background: var(--fg); }
.message { display: block; margin-top: 3px; font-size: 12px; max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.actions { white-space: nowrap; }
.actions > * + * { margin-left: 8px; }
.btn {
  display: inline-flex; align-items: center; height: 30px; padding: 0 12px; border: none;
  border-radius: var(--ag-r-8); background: var(--s3); color: var(--fg); font: inherit;
  font-size: 12.5px; font-weight: 600; cursor: pointer; text-decoration: none;
}
.btn:hover { background: var(--s4); }
.btn.is-danger { background: var(--err-soft); color: var(--err); }
.confirm { display: inline-flex; align-items: center; gap: 6px; }
.confirm-text { font-size: 12.5px; color: var(--fg); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>
