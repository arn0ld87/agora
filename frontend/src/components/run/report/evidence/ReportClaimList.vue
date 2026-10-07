<script setup lang="ts">
/**
 * Claim-Liste des Berichts (Etappe 5, #1804, Bauplan 4.6), nach Abschnitten
 * gruppiert. Der gespeicherte Lesetext ist ein Block ohne Claim-Anker; Claims im
 * Fließtext sind deshalb nicht anklickbar, die Auswahl läuft über diese Liste.
 *
 * Prop   `sections`          Claims je Abschnitt (`deriveClaimSections`)
 * Prop   `selectedClaimId`   gewählter Claim (`?claim=`), markiert per `aria-current`
 * Emit   `select(claimId | null)`  erneuter Klick auf den gewählten Claim hebt die Auswahl auf
 *
 * Claim, Hypothese und Datenlücke haben getrennte Listen mit eigener Erklärung.
 * Die Confidence steht als Text, nie nur als Farbe.
 */
import { computed, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { SectionClaims } from '@/composables/run/report/reportClaims'

const props = defineProps<{ sections: SectionClaims[]; selectedClaimId: string | null }>()
const emit = defineEmits<{ select: [claimId: string | null] }>()
const { t } = useI18n()

const total = computed(() => props.sections.reduce((n, s) => n + s.claims.length, 0))
const hypotheses = computed(() =>
  props.sections.flatMap((s) => s.hypotheses.map((h) => ({ ...h, sectionIndex: s.sectionIndex }))),
)
const gaps = computed(() => props.sections.flatMap((s) => s.dataGaps.map((g) => ({ ...g, sectionIndex: s.sectionIndex }))))

function percent(score: number): number {
  return Math.round(score * 100)
}

function pick(claimId: string): void {
  emit('select', claimId === props.selectedClaimId ? null : claimId)
}

watch(
  () => props.selectedClaimId,
  async (id) => {
    if (!id) return
    await nextTick()
    const el = document.getElementById(`report-claim-${id}`)
    if (el && typeof el.scrollIntoView === 'function') el.scrollIntoView({ block: 'nearest' })
  },
  { immediate: true, flush: 'post' },
)
</script>

<template>
  <section class="rcl" :aria-labelledby="'report-claims-title'" data-testid="report-claims">
    <h3 id="report-claims-title" class="rcl__title">
      {{ t('views.run.report.claims.title') }}
      <span class="rcl__count">{{ t('views.run.report.claims.count', { n: total }, total) }}</span>
    </h3>
    <p v-if="total === 0" class="rcl__note" data-testid="report-claims-none">{{ t('views.run.report.claims.none') }}</p>

    <div class="rcl__scroll">
      <template v-for="section in sections" :key="section.sectionIndex">
        <section v-if="section.claims.length > 0" :aria-labelledby="`report-claims-section-${section.sectionIndex}`" data-testid="report-claims-section">
          <h4 :id="`report-claims-section-${section.sectionIndex}`" class="rcl__section">
            {{ t('views.run.report.claims.sectionLabel', { n: section.sectionIndex, title: section.sectionTitle }) }}
          </h4>
          <ul class="rcl__list">
            <li v-for="claim in section.claims" :key="claim.claimId">
              <button
                :id="`report-claim-${claim.claimId}`"
                type="button"
                class="rcl__claim"
                :aria-current="claim.claimId === selectedClaimId ? 'true' : undefined"
                :data-claim="claim.claimId"
                data-testid="report-claim"
                @click="pick(claim.claimId)"
              >
                <span class="rcl__text">{{ claim.text }}</span>
                <span class="rcl__meta">
                  {{
                    t('views.run.report.claims.confidenceLine', {
                      label: t(`views.run.report.claims.confidence.${claim.confidenceLabel}`),
                      pct: percent(claim.confidenceScore),
                    })
                  }}
                  ·
                  {{ t('views.run.report.claims.evidenceCount', { n: claim.evidence.length }, claim.evidence.length) }}
                </span>
                <span v-if="claim.kinds.length > 0" class="rcl__meta" data-testid="report-claim-kinds">
                  {{ claim.kinds.map((k) => t(`views.run.report.evidence.kind.${k}`)).join(', ') }}
                </span>
              </button>
            </li>
          </ul>
        </section>
      </template>
    </div>

    <section v-if="hypotheses.length > 0" aria-labelledby="report-hypotheses-title" class="rcl__other" data-testid="report-hypotheses">
      <h4 id="report-hypotheses-title" class="rcl__section">
        {{ t('views.run.report.claims.hypotheses.title', { n: hypotheses.length }) }}
      </h4>
      <p class="rcl__note">{{ t('views.run.report.claims.hypotheses.hint') }}</p>
      <ul class="rcl__list">
        <li v-for="h in hypotheses" :key="h.hypothesis_id" class="rcl__item">
          <span class="rcl__text">{{ h.hypothesis_text }}</span>
          <span class="rcl__meta">{{ t('views.run.report.claims.hypotheses.rationale', { text: h.rationale }) }}</span>
        </li>
      </ul>
    </section>

    <section v-if="gaps.length > 0" aria-labelledby="report-gaps-title" class="rcl__other" data-testid="report-gaps">
      <h4 id="report-gaps-title" class="rcl__section">{{ t('views.run.report.claims.gaps.title', { n: gaps.length }) }}</h4>
      <p class="rcl__note">{{ t('views.run.report.claims.gaps.hint') }}</p>
      <ul class="rcl__list">
        <li v-for="g in gaps" :key="g.gap_id" class="rcl__item">
          <span class="rcl__text">{{ g.claim_text }}</span>
          <span class="rcl__meta">{{ t('views.run.report.claims.gaps.reason', { text: g.gap_reason }) }}</span>
        </li>
      </ul>
    </section>
  </section>
</template>

<style scoped>
.rcl {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}
.rcl__title {
  margin: 0;
  font-size: 13px;
  font-weight: 650;
  color: var(--fg);
}
.rcl__count {
  margin-left: 6px;
  font-weight: 500;
  color: var(--fg3);
}
.rcl__note {
  margin: 0;
  font-size: 12px;
  color: var(--fg2);
}
.rcl__scroll {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 46vh;
  overflow-y: auto;
}
.rcl__section {
  margin: 0 0 4px;
  font-size: 12px;
  font-weight: 650;
  color: var(--fg3);
}
.rcl__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.rcl__claim {
  display: flex;
  flex-direction: column;
  gap: 3px;
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s2);
  color: var(--fg);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.rcl__claim:hover {
  background: var(--s3);
}
.rcl__claim[aria-current='true'] {
  border-color: var(--acc-line);
  background: var(--s3);
}
.rcl__claim:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.rcl__item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 8px 10px;
  border: 1px dashed var(--line);
  border-radius: var(--ag-r-8);
}
.rcl__text {
  font-size: 13px;
  line-height: 1.4;
}
.rcl__meta {
  font-size: 12px;
  color: var(--fg2);
}
.rcl__other {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
