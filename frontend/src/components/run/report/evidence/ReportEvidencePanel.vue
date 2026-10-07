<script setup lang="ts">
/**
 * Inhalt des Bereichs „Belege“ der Seitenspalte (Slot `evidence` von
 * `ReportSidePane`, Etappe 5, #1804, Bauplan 4.6). Reihenfolge: Kennzahlen,
 * Belege des gewählten Claims (ohne Auswahl Hinweis und Übersicht), Claim-Liste,
 * Prüfhinweise. Die Hinweise zu `evidence_omitted` und Ladefehlern stehen schon
 * über dem Slot in `ReportSidePane`.
 *
 * Daten: `useRunReportContext()` (`report`, `evidence`, `selectedClaimId`,
 * `selectClaim`); Kennzahlen über `useReportArtifacts`.
 *
 * Prop `artifactsApi`  Austausch der beiden Artefakt-Abrufe (Tests)
 * Slot `jump`          (Prop `item`) Sprung an den Ursprung eines Belegs
 */
import { computed } from 'vue'
import { useRunReportContext } from '@/composables/run/report/useRunReport'
import {
  deriveChecks,
  deriveClaimSections,
  findClaim,
  SOURCE_KIND_ORDER,
  type ClaimEvidenceView,
} from '@/composables/run/report/reportClaims'
import { useReportArtifacts, type ReportArtifactsApi } from '@/composables/run/report/useReportArtifacts'
import ReportChecks from './ReportChecks.vue'
import ReportClaimList from './ReportClaimList.vue'
import ReportEvidenceList from './ReportEvidenceList.vue'
import ReportMetrics from './ReportMetrics.vue'

const props = defineProps<{ artifactsApi?: Partial<ReportArtifactsApi> }>()
defineSlots<{ jump?: (p: { item: ClaimEvidenceView }) => unknown }>()
const ctx = useRunReportContext()

const TERMINAL = new Set(['completed', 'incomplete'])
const finished = computed(() => ctx.report.value.status === 'ok' && TERMINAL.has(ctx.report.value.report.status))

const artifacts = useReportArtifacts({
  reportId: () => (finished.value ? ctx.selectedReportId.value : null),
  enabled: () => finished.value,
  api: props.artifactsApi,
})

const map = computed(() => (ctx.evidence.value.status === 'ok' ? ctx.evidence.value.map : null))
const sections = computed(() => (map.value ? deriveClaimSections(map.value) : []))
const claim = computed(() => findClaim(sections.value, ctx.selectedClaimId.value))
const checks = computed(() => (map.value ? deriveChecks(map.value) : null))
const overview = computed(() => {
  const index = map.value?.evidence_index ?? {}
  const counts = new Map<string, number>()
  for (const rec of Object.values(index)) counts.set(rec.source_kind, (counts.get(rec.source_kind) ?? 0) + 1)
  return SOURCE_KIND_ORDER.filter((k) => counts.has(k)).map((kind) => ({ kind, count: counts.get(kind) ?? 0 }))
})
</script>

<template>
  <div v-if="finished" class="rep" data-testid="report-evidence-panel">
    <ReportMetrics :density="artifacts.density.value" :stance="artifacts.stance.value" />
    <template v-if="map">
      <ReportEvidenceList :claim="claim" :overview="overview">
        <template #jump="{ item }"><slot name="jump" :item="item" /></template>
      </ReportEvidenceList>
      <ReportClaimList :sections="sections" :selected-claim-id="ctx.selectedClaimId.value" @select="ctx.selectClaim" />
      <ReportChecks v-if="checks" :checks="checks" />
    </template>
  </div>
</template>

<style scoped>
.rep {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}
</style>
