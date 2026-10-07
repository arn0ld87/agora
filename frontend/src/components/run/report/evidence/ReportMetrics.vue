<script setup lang="ts">
/**
 * Kennzahlen des Berichts (Etappe 5, #1804): Belegdichte und Positionierungsquote.
 * Jede Kennzahl zeigt alle Zustände: Daten, „für diese Fassung nicht gespeichert“
 * (404, Altbericht) und die sichtbare Auslassung `artifact_omitted` (Datei
 * verletzt den Vertrag, nie eine Datenlücke). Ein Lauf ohne Streitfrage
 * (`applicable=false`) steht als solcher da und ist kein Fehler.
 */
import { useI18n } from 'vue-i18n'
import type { ArtifactState } from '@/composables/run/report/useReportArtifacts'
import type { EvidenceDensity } from '@/contracts/evidenceDensityContract'
import type { StanceAnalysis } from '@/contracts/stanceAnalysisContract'

defineProps<{ density: ArtifactState<EvidenceDensity>; stance: ArtifactState<StanceAnalysis> }>()
const { t } = useI18n()

function pct(ratio: number | null | undefined): string {
  return ratio === null || ratio === undefined ? '–' : `${Math.round(ratio * 100)} %`
}
</script>

<template>
  <section class="rm" aria-labelledby="report-metrics-title" data-testid="report-metrics">
    <h3 id="report-metrics-title" class="rm__title">{{ t('views.run.report.metrics.title') }}</h3>

    <section class="rm__block" aria-labelledby="report-density-title" data-testid="report-density">
      <h4 id="report-density-title" class="rm__sub">{{ t('views.run.report.metrics.density.title') }}</h4>
      <p v-if="density.status === 'idle' || density.status === 'loading'" class="rm__note" role="status">
        {{ t('views.run.report.metrics.loading') }}
      </p>
      <p v-else-if="density.status === 'unsaved'" class="rm__note" data-testid="report-density-unsaved">
        {{ t('views.run.report.metrics.unsaved') }}
      </p>
      <div v-else-if="density.status === 'omitted'" class="rm__omitted" role="alert" data-testid="report-density-omitted">
        <p class="rm__omitted-title">{{ t('views.run.report.metrics.omitted.title', { name: t('views.run.report.metrics.density.title') }) }}</p>
        <p class="rm__note">{{ t('views.run.report.metrics.omitted.body') }}</p>
        <ul v-if="density.omission.validation_errors.length > 0" class="rm__errors">
          <li v-for="e in density.omission.validation_errors" :key="e">{{ e }}</li>
        </ul>
      </div>
      <p v-else-if="density.status === 'failed'" class="rm__problem" role="alert" data-testid="report-density-failed">
        {{ t('views.run.report.metrics.failed', { reason: density.reason }) }}
      </p>
      <template v-else>
        <p v-if="density.data.claims_total === 0" class="rm__note" data-testid="report-density-empty">
          {{ t('views.run.report.metrics.density.noClaims') }}
        </p>
        <dl v-else class="rm__list" data-testid="report-density-data">
          <div><dt>{{ t('views.run.report.metrics.density.claimsTotal') }}</dt><dd>{{ density.data.claims_total }}</dd></div>
          <div><dt>{{ t('views.run.report.metrics.density.without') }}</dt><dd>{{ density.data.claims_without_support }}</dd></div>
          <div><dt>{{ t('views.run.report.metrics.density.single') }}</dt><dd>{{ density.data.claims_single_support }}</dd></div>
          <div><dt>{{ t('views.run.report.metrics.density.multi') }}</dt><dd>{{ density.data.claims_multi_support }}</dd></div>
          <div><dt>{{ t('views.run.report.metrics.density.multiIndependent') }}</dt><dd>{{ density.data.claims_multi_independent }}</dd></div>
          <div><dt>{{ t('views.run.report.metrics.density.singleRatio') }}</dt><dd>{{ pct(density.data.single_support_ratio) }}</dd></div>
        </dl>
      </template>
    </section>

    <section class="rm__block" aria-labelledby="report-stance-title" data-testid="report-stance">
      <h4 id="report-stance-title" class="rm__sub">{{ t('views.run.report.metrics.stance.title') }}</h4>
      <p v-if="stance.status === 'idle' || stance.status === 'loading'" class="rm__note" role="status">
        {{ t('views.run.report.metrics.loading') }}
      </p>
      <p v-else-if="stance.status === 'unsaved'" class="rm__note" data-testid="report-stance-unsaved">
        {{ t('views.run.report.metrics.unsaved') }}
      </p>
      <div v-else-if="stance.status === 'omitted'" class="rm__omitted" role="alert" data-testid="report-stance-omitted">
        <p class="rm__omitted-title">{{ t('views.run.report.metrics.omitted.title', { name: t('views.run.report.metrics.stance.title') }) }}</p>
        <p class="rm__note">{{ t('views.run.report.metrics.omitted.body') }}</p>
        <ul v-if="stance.omission.validation_errors.length > 0" class="rm__errors">
          <li v-for="e in stance.omission.validation_errors" :key="e">{{ e }}</li>
        </ul>
      </div>
      <p v-else-if="stance.status === 'failed'" class="rm__problem" role="alert" data-testid="report-stance-failed">
        {{ t('views.run.report.metrics.failed', { reason: stance.reason }) }}
      </p>
      <p v-else-if="!stance.data.applicable" class="rm__note" data-testid="report-stance-not-applicable">
        {{ t('views.run.report.metrics.stance.notApplicable') }}
      </p>
      <template v-else>
        <p v-if="stance.data.contested_statement" class="rm__note" data-testid="report-stance-statement">
          {{ t('views.run.report.metrics.stance.contested', { text: stance.data.contested_statement }) }}
        </p>
        <p class="rm__ratio" data-testid="report-stance-data">
          {{
            t('views.run.report.metrics.stance.ratio', {
              positioned: stance.data.voices_positioned,
              total: stance.data.voices_total,
              pct: pct(stance.data.positioning_ratio),
            })
          }}
        </p>
        <ul class="rm__camps" data-testid="report-stance-camps">
          <li v-for="camp in (['in_favour', 'opposed', 'undecided'] as const)" :key="camp">
            {{ t(`views.run.report.metrics.stance.camps.${camp}`) }}: {{ stance.data.camp_distribution[camp] ?? 0 }}
          </li>
        </ul>
        <p v-if="stance.data.classification_failed > 0" class="rm__problem" data-testid="report-stance-unclassified">
          {{ t('views.run.report.metrics.stance.unclassified', { n: stance.data.classification_failed }, stance.data.classification_failed) }}
        </p>
      </template>
    </section>
  </section>
</template>

<style scoped>
.rm {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}
.rm__title {
  margin: 0;
  font-size: 13px;
  font-weight: 650;
  color: var(--fg);
}
.rm__block {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s2);
}
.rm__sub {
  margin: 0;
  font-size: 12px;
  font-weight: 650;
  color: var(--fg3);
}
.rm__note {
  margin: 0;
  font-size: 12px;
  color: var(--fg2);
}
.rm__problem {
  margin: 0;
  font-size: 12px;
  color: var(--err);
}
.rm__ratio {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--fg);
}
.rm__camps {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--fg2);
}
.rm__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  font-size: 12px;
  color: var(--fg2);
}
.rm__list div {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}
.rm__list dd {
  margin: 0;
  font-weight: 600;
  color: var(--fg);
}
.rm__omitted {
  padding: 8px 10px;
  border: 1px solid var(--warn);
  border-radius: var(--ag-r-8);
  background: var(--warn-soft);
  color: var(--fg);
}
.rm__omitted-title {
  margin: 0 0 2px;
  font-size: 12px;
  font-weight: 650;
}
.rm__errors {
  margin: 4px 0 0;
  padding-left: 18px;
  font-size: 12px;
}
</style>
