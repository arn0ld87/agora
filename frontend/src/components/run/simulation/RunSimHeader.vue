<script setup lang="ts">
/**
 * Kopf der Simulation am Lauf (#1801, Bauplan 4.5): Zustand, Runde x von y,
 * Beiträge, Kosten, Modell und die Steuerung passend zum Zustand. Der Zustand
 * steht als Text und Symbol, die Farbe kommt nur dazu. Stopp, Budgetabbruch und
 * Fehlschlag nennen ihren Grund und sehen nie wie ein Erfolg aus. Das Modell ist
 * reiner Text; die Wahl liegt im Startdialog bzw. in den Einstellungen.
 */
import { computed, ref, toRef } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
  DialogTrigger,
} from 'reka-ui'
import RunStateMark from '@/components/run/RunStateMark.vue'
import { useSimulationRunStateContext } from '@/composables/run/simulation/useSimulationRunStateContext'
import { useSimulationControl } from '@/composables/run/simulation/useSimulationControl'
import { formatCostMicros } from '@/utils/format'

const props = withDefaults(
  defineProps<{
    simulationId: string
    /** RunRegistry-ID des Simulationsjobs (Kosten, Abbruchgrund). */
    runId?: string | null
    /** Gelaufene Route des Simulationsjobs (`jobs.simulation_run.route`). */
    route?: { model: string; providerId: string } | null
    /** Personas fertig vorbereitet; sonst ist Starten gesperrt. */
    personasReady?: boolean
  }>(),
  { runId: null, route: null, personasReady: true },
)
const emit = defineEmits<{
  /** Start erfolgreich; `runId` aus der Startantwort. */
  started: [runId: string | null]
  /** Stopp, Pause oder Fortsetzen ist durch (der Arbeitsbereich kann neu laden). */
  changed: []
}>()
const { t, te, locale } = useI18n()

const idRef = toRef(props, 'simulationId')
const state = useSimulationRunStateContext(() => idRef.value, { runId: () => props.runId })
const control = useSimulationControl(() => idRef.value)

const kind = state.stateKind
const stopOpen = ref(false)

const ACTIVE_KINDS = new Set(['queued', 'running', 'paused'])
const isActive = computed(() => ACTIVE_KINDS.has(kind.value))
const canPause = computed(() => kind.value === 'running')
const canResume = computed(() => kind.value === 'paused')
const canStart = computed(() => kind.value === 'notStarted')
const blocked = computed(() => canStart.value && !props.personasReady)

const roundText = computed(() => {
  const current = state.currentRound.value
  const total = state.totalRounds.value
  if (kind.value === 'notStarted' || current === null) return t('views.run.simHeader.roundNone')
  if (!total) return t('views.run.simHeader.roundTotalUnknown', { current })
  return t('views.run.simHeader.round', { current, total })
})

const postsText = computed(() => {
  const total = state.totalActions.value
  if (total === null) return t('views.run.simHeader.notRecorded')
  return t('views.run.simHeader.posts', {
    total,
    twitter: state.twitterActions.value ?? 0,
    reddit: state.redditActions.value ?? 0,
  })
})

const costText = computed(() => {
  const micros = state.costMicros.value
  return micros === null ? t('views.run.simHeader.notRecorded') : formatCostMicros(micros, 'USD', locale.value)
})

const modelText = computed(() => {
  if (kind.value === 'notStarted') {
    const planned = control.plannedModel()
    return planned ? t('views.run.simHeader.modelPlanned', { model: planned }) : t('views.run.simHeader.modelNone')
  }
  return props.route?.model || t('views.run.simHeader.notRecorded')
})

const reasonText = computed<string | null>(() => {
  const k = kind.value
  if (k !== 'stopped' && k !== 'budget' && k !== 'failed') return null
  const code = state.terminationReason.value
  const key = code ? `views.run.termination.${code}` : ''
  const label = code ? (te(key) ? t(key) : code) : ''
  const detail = k === 'failed' && state.runError.value ? state.runError.value : ''
  const reason = [label, detail].filter(Boolean).join(': ') || t('views.run.simHeader.reasonUnknown')
  const slot = k === 'budget' ? 'reasonBudget' : k === 'failed' ? 'reasonFailed' : 'reasonStopped'
  return t(`views.run.simHeader.${slot}`, { reason })
})

const errors = computed(() => {
  const out: string[] = []
  if (control.error.value) out.push(control.error.value)
  if (state.error.value) out.push(state.error.value)
  return out
})

const liveText = computed(() => {
  const label = t(`views.run.state.${kind.value}`)
  return [t('views.run.simHeader.live', { state: label }), reasonText.value].filter(Boolean).join('. ')
})

async function doStart(): Promise<void> {
  const res = await control.start()
  if (!res) return
  await state.adoptRunId(res.runId)
  emit('started', res.runId)
}
async function doPause(): Promise<void> {
  if (await control.pause()) {
    await state.reload()
    emit('changed')
  }
}
async function doResume(): Promise<void> {
  if (await control.resume()) {
    await state.reload()
    emit('changed')
  }
}
async function doStop(): Promise<void> {
  const ok = await control.stop()
  stopOpen.value = false
  if (ok) {
    await state.reload()
    emit('changed')
  }
}
</script>

<template>
  <section class="sim-head" :aria-label="t('views.run.simHeader.ariaLabel')" data-testid="sim-header">
    <div class="sim-head__top">
      <RunStateMark :state="kind" />
      <dl class="sim-head__facts">
        <div class="sim-head__fact">
          <dt class="sr-only">{{ t('views.run.simHeader.roundLabel') }}</dt>
          <dd data-testid="sim-header-round">{{ roundText }}</dd>
        </div>
        <div class="sim-head__fact">
          <dt>{{ t('views.run.simHeader.postsLabel') }}</dt>
          <dd data-testid="sim-header-posts">{{ postsText }}</dd>
        </div>
        <div class="sim-head__fact">
          <dt>{{ t('views.run.simHeader.costLabel') }}</dt>
          <dd data-testid="sim-header-cost">{{ costText }}</dd>
        </div>
        <div class="sim-head__fact">
          <dt>{{ t('views.run.simHeader.modelLabel') }}</dt>
          <dd data-testid="sim-header-model">{{ modelText }}</dd>
        </div>
      </dl>
      <div class="sim-head__actions">
        <button
          v-if="canStart"
          type="button"
          class="sim-head__btn sim-head__btn--primary"
          :disabled="blocked || control.busy.value !== null"
          :aria-describedby="blocked ? 'sim-head-blocked' : undefined"
          data-testid="sim-header-start"
          @click="doStart"
        >
          {{ control.busy.value === 'start' ? t('views.run.simHeader.starting') : t('views.run.simHeader.start') }}
        </button>
        <button
          v-if="canPause"
          type="button"
          class="sim-head__btn"
          :disabled="control.busy.value !== null"
          data-testid="sim-header-pause"
          @click="doPause"
        >
          {{ control.busy.value === 'pause' ? t('views.run.simHeader.pausing') : t('views.run.simHeader.pause') }}
        </button>
        <button
          v-if="canResume"
          type="button"
          class="sim-head__btn sim-head__btn--primary"
          :disabled="control.busy.value !== null"
          data-testid="sim-header-resume"
          @click="doResume"
        >
          {{ control.busy.value === 'resume' ? t('views.run.simHeader.resuming') : t('views.run.simHeader.resume') }}
        </button>
        <DialogRoot v-if="isActive" v-model:open="stopOpen">
          <DialogTrigger as-child>
            <button
              type="button"
              class="sim-head__btn"
              :disabled="control.busy.value !== null"
              data-testid="sim-header-stop"
            >
              {{ control.busy.value === 'stop' ? t('views.run.simHeader.stopping') : t('views.run.simHeader.stop') }}
            </button>
          </DialogTrigger>
          <DialogPortal>
            <DialogOverlay class="sim-head__overlay" />
            <DialogContent class="sim-head__dialog" data-testid="sim-header-stop-dialog">
              <DialogTitle class="sim-head__dialog-title">{{ t('views.run.simHeader.stopTitle') }}</DialogTitle>
              <DialogDescription class="sim-head__dialog-desc">
                {{ t('views.run.simHeader.stopDescription') }}
              </DialogDescription>
              <div class="sim-head__dialog-actions">
                <DialogClose as-child>
                  <button type="button" class="sim-head__btn" data-testid="sim-header-stop-cancel">
                    {{ t('views.run.simHeader.stopCancel') }}
                  </button>
                </DialogClose>
                <button
                  type="button"
                  class="sim-head__btn sim-head__btn--primary"
                  :disabled="control.busy.value !== null"
                  data-testid="sim-header-stop-confirm"
                  @click="doStop"
                >
                  {{ control.busy.value === 'stop' ? t('views.run.simHeader.stopping') : t('views.run.simHeader.stopConfirm') }}
                </button>
              </div>
            </DialogContent>
          </DialogPortal>
        </DialogRoot>
      </div>
    </div>

    <p v-if="reasonText" class="sim-head__reason" data-testid="sim-header-reason">{{ reasonText }}</p>
    <p v-if="blocked" id="sim-head-blocked" class="sim-head__hint" data-testid="sim-header-blocked">
      {{ t('views.run.simHeader.blockedPersonas') }}
    </p>
    <p
      v-for="(message, i) in errors"
      :key="i"
      class="sim-head__error"
      role="alert"
      data-testid="sim-header-error"
    >
      {{ t('views.run.simHeader.error', { message }) }}
    </p>
    <div class="sr-only" aria-live="polite" data-testid="sim-header-live">{{ liveText }}</div>
  </section>
</template>

<style scoped>
.sim-head {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 16px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg);
}
.sim-head__top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 20px;
}
.sim-head__facts {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 20px;
  margin: 0;
  flex: 1 1 auto;
  font-size: 13px;
}
.sim-head__fact {
  display: flex;
  gap: 6px;
  align-items: baseline;
}
.sim-head__fact dt {
  color: var(--fg3);
  font-size: 12px;
  font-weight: 600;
}
.sim-head__fact dd {
  margin: 0;
  color: var(--fg);
}
.sim-head__actions {
  display: flex;
  gap: 8px;
}
.sim-head__btn {
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.sim-head__btn--primary {
  background: var(--acc);
  border-color: var(--acc);
  color: var(--on-acc);
}
.sim-head__btn:disabled {
  color: var(--fg3);
  background: var(--s3);
  border-color: var(--line);
  cursor: not-allowed;
}
.sim-head__btn:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.sim-head__reason {
  margin: 0;
  padding: 6px 10px;
  border-radius: var(--ag-r-8);
  background: var(--warn-soft);
  color: var(--warn);
  font-size: 13px;
  font-weight: 600;
}
.sim-head__hint {
  margin: 0;
  font-size: 13px;
  color: var(--fg2);
}
.sim-head__error {
  margin: 0;
  padding: 6px 10px;
  border-radius: var(--ag-r-8);
  background: var(--err-soft);
  color: var(--err);
  font-size: 13px;
}
.sim-head__overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 60;
}
.sim-head__dialog {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 61;
  width: min(440px, calc(100vw - 32px));
  padding: 20px;
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.sim-head__dialog-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.sim-head__dialog-desc {
  margin: 0;
  font-size: 13px;
  color: var(--fg2);
}
.sim-head__dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
