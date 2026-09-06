<!--
  DegradationNotice — macht stille Teilausfälle sichtbar (Issue #1029).

  Ein Pipeline-Schritt kann durchlaufen und trotzdem ein Ergebnis liefern,
  mit dem weiterzuarbeiten sich nicht lohnt: Embedding ausgefallen, Graph
  ohne Kanten, Personas als regelbasierte Platzhalter. Bis #1029 meldeten
  alle drei Fälle schlicht Erfolg.

  Die Komponente rendert nichts, solange nichts ausgefallen ist — der
  Normalfall bleibt ruhig. `blocking` bedeutet, dass der Schritt den
  Zustand „bereit“ nicht erreicht; `warning` heißt, das Ergebnis ist
  nutzbar, aber nachweislich schlechter als es aussieht.
-->
<template>
  <section
    v-if="report.events.length > 0"
    class="degradation-notice"
    :data-severity="overallSeverity"
    role="alert"
    aria-live="polite"
  >
    <h3 class="degradation-notice__title">
      {{ t(`degradation.title.${overallSeverity}`) }}
    </h3>
    <ul class="degradation-notice__list">
      <li v-for="event in report.events" :key="`${event.kind}-${event.occurred_at}`">
        <p class="degradation-notice__kind">
          {{ t(`degradation.kind.${event.kind}`) }}
          <span v-if="event.occurrences > 1" class="degradation-notice__count">
            {{ t('degradation.occurrences', { count: event.occurrences }) }}
          </span>
        </p>
        <!-- detail kommt aus dem Backend: Ursache im Klartext, keine UI-Kopie. -->
        <p class="degradation-notice__detail">{{ event.detail }}</p>
        <p class="degradation-notice__action">{{ t(`degradation.action.${event.kind}`) }}</p>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PipelineDegradationReport } from '@/contracts/pipelineDegradationContract'
import { hasBlockingDegradation } from '@/contracts/pipelineDegradationContract'

const props = defineProps<{
  report: PipelineDegradationReport
}>()

const { t } = useI18n()

/** Ein einziges blockierendes Ereignis färbt den ganzen Hinweis. */
const overallSeverity = computed(() =>
  hasBlockingDegradation(props.report) ? 'blocking' : 'warning',
)
</script>

<style scoped>
.degradation-notice {
  border: 1px solid var(--warn, var(--status-orange));
  border-radius: var(--r-5);
  padding: 12px 16px;
  background: var(--warn-soft, var(--status-orange-bg));
}

.degradation-notice[data-severity='blocking'] {
  border-color: var(--status-error, var(--status-red));
  background: var(--status-error-soft, var(--status-red-bg));
}

.degradation-notice__title {
  margin: 0 0 8px;
  font-size: 0.95rem;
  font-weight: 600;
}

.degradation-notice__list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.degradation-notice__kind {
  margin: 0;
  font-weight: 600;
  font-size: 0.9rem;
}

.degradation-notice__count {
  font-weight: 400;
  opacity: 0.75;
  margin-left: 6px;
}

.degradation-notice__detail,
.degradation-notice__action {
  margin: 2px 0 0;
  font-size: 0.85rem;
}

.degradation-notice__action {
  opacity: 0.85;
}
</style>
