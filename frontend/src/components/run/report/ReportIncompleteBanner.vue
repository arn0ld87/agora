<script setup lang="ts">
/**
 * Hinweisband „Was fehlt“ (Etappe 5, #1804, Bauplan 4.6), direkt unter dem Kopf
 * und ohne Scrollen sichtbar. Erscheint bei Status `incomplete` oder sobald der
 * Bericht `missing_sections` bzw. `run_degradations` trägt. „Unvollständig“ wird
 * nie als fertig dargestellt; der Zustand steht als Text, die Farbe kommt dazu.
 * Blockierende Degradationen sind hervorgehoben und als solche benannt.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Report } from '@/contracts/reportContract'

const props = defineProps<{ report: Report | null }>()
const { t, te } = useI18n()

const missing = computed(() => props.report?.missing_sections ?? [])
const degradations = computed(() => props.report?.run_degradations ?? [])
const visible = computed(
  () => !!props.report && (props.report.status === 'incomplete' || missing.value.length > 0 || degradations.value.length > 0),
)
const incomplete = computed(() => props.report?.status === 'incomplete')
/** Unvollständig ohne jede Einzelangabe: das sagt das Band ehrlich. */
const noDetail = computed(() => incomplete.value && missing.value.length === 0 && degradations.value.length === 0)

function componentLabel(component: string): string {
  const key = `views.run.degradation.${component}`
  return te(key) ? t(key) : component
}
</script>

<template>
  <section
    v-if="visible"
    class="rr-banner"
    :class="{ 'rr-banner--incomplete': incomplete }"
    role="status"
    :aria-label="t('views.run.report.banner.label')"
    data-testid="report-banner"
  >
    <h2 class="rr-banner__title">
      {{ incomplete ? t('views.run.report.banner.titleIncomplete') : t('views.run.report.banner.titleNotes') }}
    </h2>
    <p v-if="noDetail" class="rr-banner__text" data-testid="report-banner-nodetail">
      {{ t('views.run.report.banner.noDetail') }}
    </p>

    <template v-if="missing.length > 0">
      <p class="rr-banner__sub">{{ t('views.run.report.banner.missingSections', { n: missing.length }, missing.length) }}</p>
      <ul class="rr-banner__list" data-testid="report-banner-missing">
        <li v-for="title in missing" :key="title">{{ title }}</li>
      </ul>
    </template>

    <template v-if="degradations.length > 0">
      <p class="rr-banner__sub">{{ t('views.run.report.banner.degradations') }}</p>
      <ul class="rr-banner__list" data-testid="report-banner-degradations">
        <li
          v-for="(d, i) in degradations"
          :key="`${d.component}-${i}`"
          :class="{ 'rr-banner__item--blocking': d.severity === 'blocking' }"
          :data-severity="d.severity"
        >
          <span class="rr-banner__tag">{{
            d.severity === 'blocking' ? t('views.run.report.banner.blocking') : t('views.run.report.banner.warning')
          }}</span>
          <strong>{{ componentLabel(d.component) }}</strong>
          <span v-if="d.detail"> · {{ d.detail }}</span>
          <span v-else> · {{ d.reason }}</span>
        </li>
      </ul>
    </template>
  </section>
</template>

<style scoped>
.rr-banner {
  padding: 10px 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg);
}
.rr-banner--incomplete {
  border-color: var(--warn);
  background: var(--warn-soft);
}
.rr-banner__title {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 650;
}
.rr-banner__text,
.rr-banner__sub {
  margin: 4px 0 2px;
  font-size: 13px;
}
.rr-banner__sub {
  font-weight: 600;
  color: var(--fg2);
}
.rr-banner__list {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
}
.rr-banner__tag {
  display: inline-block;
  margin-right: 6px;
  padding: 0 6px;
  border-radius: var(--ag-r-pill);
  background: var(--s3);
  color: var(--fg2);
  font-size: 11px;
  font-weight: 600;
}
.rr-banner__item--blocking {
  font-weight: 600;
}
.rr-banner__item--blocking .rr-banner__tag {
  background: var(--err-soft);
  color: var(--err);
}
</style>
