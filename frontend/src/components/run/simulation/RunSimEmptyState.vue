<script setup lang="ts">
/**
 * Leerzustand "noch nicht gestartet" (#1801, Bauplan 4.5): zwei Sätze zur
 * Erklärung (synthetische Äußerungen, keine Vorhersage), das Modell des
 * nächsten Starts als Text und der Startknopf. Ohne fertige Personas ist der
 * Knopf gesperrt und nennt den Grund.
 */
import { toRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSimulationControl } from '@/composables/run/simulation/useSimulationControl'

const props = withDefaults(defineProps<{ simulationId: string; personasReady?: boolean }>(), {
  personasReady: true,
})
const emit = defineEmits<{ started: [runId: string | null] }>()
const { t } = useI18n()

const idRef = toRef(props, 'simulationId')
const control = useSimulationControl(() => idRef.value)

function modelText(): string {
  const planned = control.plannedModel()
  return planned ? t('views.run.simHeader.modelPlanned', { model: planned }) : t('views.run.simHeader.modelNone')
}

async function doStart(): Promise<void> {
  const res = await control.start()
  if (res) emit('started', res.runId)
}
</script>

<template>
  <section class="sim-empty" data-testid="sim-empty">
    <h3 class="sim-empty__title">{{ t('views.run.simHeader.empty.title') }}</h3>
    <p class="sim-empty__text">
      {{ t('views.run.simHeader.empty.explainRounds') }}
      {{ t('views.run.simHeader.empty.explainSynthetic') }}
    </p>
    <p class="sim-empty__model" data-testid="sim-empty-model">
      <span class="sim-empty__label">{{ t('views.run.simHeader.modelLabel') }}</span>
      {{ modelText() }}
    </p>
    <button
      type="button"
      class="sim-empty__btn"
      :disabled="!personasReady || control.busy.value !== null"
      :aria-describedby="!personasReady ? 'sim-empty-blocked' : undefined"
      data-testid="sim-empty-start"
      @click="doStart"
    >
      {{ control.busy.value === 'start' ? t('views.run.simHeader.starting') : t('views.run.simHeader.start') }}
    </button>
    <p v-if="!personasReady" id="sim-empty-blocked" class="sim-empty__hint" data-testid="sim-empty-blocked">
      {{ t('views.run.simHeader.blockedPersonas') }}
    </p>
    <p v-if="control.error.value" class="sim-empty__error" role="alert" data-testid="sim-empty-error">
      {{ t('views.run.simHeader.error', { message: control.error.value }) }}
    </p>
  </section>
</template>

<style scoped>
.sim-empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  max-width: 560px;
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg);
}
.sim-empty__title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.sim-empty__text {
  margin: 0;
  font-size: 13px;
  color: var(--fg2);
}
.sim-empty__model {
  margin: 0;
  font-size: 13px;
}
.sim-empty__label {
  margin-right: 6px;
  color: var(--fg3);
  font-size: 12px;
  font-weight: 600;
}
.sim-empty__btn {
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 14px;
  border: 1px solid var(--acc);
  border-radius: var(--ag-r-8);
  background: var(--acc);
  color: var(--on-acc);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.sim-empty__btn:disabled {
  color: var(--fg3);
  background: var(--s3);
  border-color: var(--line);
  cursor: not-allowed;
}
.sim-empty__btn:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.sim-empty__hint {
  margin: 0;
  font-size: 13px;
  color: var(--fg2);
}
.sim-empty__error {
  margin: 0;
  padding: 6px 10px;
  border-radius: var(--ag-r-8);
  background: var(--err-soft);
  color: var(--err);
  font-size: 13px;
}
</style>
