<script setup lang="ts">
/**
 * Dauerhafte Budgetmeldung der Interviews (#1805, Etappe 6): Das Backend lehnt
 * eine Frage mit HTTP 409 `budget_exceeded` ab, wenn der Lauf sein Budget
 * erreicht hat. Die Meldung nennt Abbruchgrund und Zahlen aus dieser Antwort
 * (nur, was dort stand) und bleibt stehen, bis eine neue Frage sie ersetzt.
 * Sie ist nie eine leere Antwort und sperrt das Eingabefeld nicht still.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRunInterviewsContext } from '@/composables/run/interviews/useRunInterviews'

const { t } = useI18n()
const ctx = useRunInterviewsContext()
const detail = computed(() => (ctx.budgetExceeded.value ? ctx.budgetDetail.value : null))
const figures = computed(() => {
  const d = detail.value
  if (!d || d.observed === null || d.threshold === null) return null
  return t('views.run.interviews.budget.figures', {
    dimension: d.dimension ?? t('views.run.interviews.budget.dimensionUnknown'),
    observed: d.observed,
    threshold: d.threshold,
  })
})
</script>

<template>
  <section v-if="ctx.budgetExceeded.value" class="bnotice" role="alert" data-testid="budget-notice">
    <h2 class="bnotice__title">{{ t('views.run.interviews.budget.title') }}</h2>
    <p class="bnotice__text">{{ t('views.run.interviews.budget.explain') }}</p>
    <p v-if="detail?.reason" class="bnotice__text" data-testid="budget-reason">
      {{ t('views.run.interviews.budget.reason', { reason: detail.reason }) }}
    </p>
    <p v-if="figures" class="bnotice__text" data-testid="budget-figures">{{ figures }}</p>
    <p v-if="detail?.message" class="bnotice__text bnotice__text--muted" data-testid="budget-message">{{ detail.message }}</p>
  </section>
</template>

<style scoped>
.bnotice {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid var(--err);
  border-radius: var(--ag-r-8);
  background: var(--err-soft);
  color: var(--err);
}
.bnotice__title {
  margin: 0;
  font-size: 14px;
  font-weight: 650;
}
.bnotice__text {
  margin: 0;
  font-size: 13px;
  overflow-wrap: anywhere;
}
.bnotice__text--muted {
  opacity: 0.85;
}
</style>
