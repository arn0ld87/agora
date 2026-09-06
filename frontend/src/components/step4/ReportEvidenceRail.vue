<script setup lang="ts">
/**
 * ReportEvidenceRail — Belegrand der Leseumgebung (PR 6, Premium-Redesign).
 *
 * Zeigt fuer den gerade sichtbaren Abschnitt: Claims mit Confidence-Wort
 * (Audit: "Confidence als Prozentzahl ohne Erklaerung" ist die geruegte
 * Praxis — hier steht das Wort immer, der Score nur ergaenzend), die daran
 * gebundenen Belege, Datenluecken und globale Red-Team-Befunde.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ReportReaderTestId } from '@/contracts/testIds'
import type {
  EvidenceIndex,
  EvidenceRecord,
  ReportClaim,
  ReportSection,
  ReportSectionHypothesis,
} from '../../contracts/reportContract'

const props = withDefaults(
  defineProps<{
    section: ReportSection | null
    sectionNum: number | null
    evidenceIndex?: EvidenceIndex
    redTeamFindings?: string[]
  }>(),
  {
    evidenceIndex: () => ({}),
    redTeamFindings: () => [],
  },
)

const emit = defineEmits<{
  navigate: [anchor: string]
}>()

const { t } = useI18n()
const testIds = ReportReaderTestId

const claims = computed<ReportClaim[]>(() => props.section?.claims ?? [])
const gaps = computed(() => props.section?.data_gaps ?? [])
// `hypotheses` ist serverseitig auf fuenf Eintraege gedeckelt; alles darueber
// landet in `hypotheses_appendix` (bis 50, ReportSectionModel im
// report_contract). Beide Listen sind derselbe Typ und dieselbe Sache — wer
// nur die erste liest, blendet den Ueberhang aus und zaehlt zu wenig.
const hypotheses = computed<ReportSectionHypothesis[]>(() => [
  ...(props.section?.hypotheses ?? []),
  ...(props.section?.hypotheses_appendix ?? []),
])

// Hypothesen sind Behauptungen ohne (ausreichende) Evidence — das Audit
// verlangt, dass Claims und Hypothesen unterscheidbar bleiben. Statt einer
// eigenen Karte bekommen sie einen zweiten Tab innerhalb desselben
// Rail-Blocks ("Aussagen in Abschnitt N"), analog zur vormaligen
// ReportEvidencePanel-Aufteilung.
const activeDetailTab = ref<'claims' | 'hypotheses'>('claims')

watch(
  () => props.section,
  () => {
    activeDetailTab.value = 'claims'
  },
)

function claimEvidence(claim: ReportClaim): EvidenceRecord[] {
  if (!Array.isArray(claim.evidence)) return []
  return claim.evidence
    .map((binding) => props.evidenceIndex[binding.evidence_id])
    .filter((record): record is EvidenceRecord => record !== undefined)
}

// Belege dieses Abschnitts, dedupliziert ueber alle Claims hinweg — der
// Belegrand zeigt sie als eine gemeinsame Liste ("Belege an dieser Stelle"),
// nicht claimweise wiederholt.
const sectionEvidence = computed<EvidenceRecord[]>(() => {
  const seen = new Set<string>()
  const out: EvidenceRecord[] = []
  for (const claim of claims.value) {
    for (const record of claimEvidence(claim)) {
      if (seen.has(record.evidence_id)) continue
      seen.add(record.evidence_id)
      out.push(record)
    }
  }
  return out
})

function confidenceWord(claim: ReportClaim): string {
  return t(`step4.reader.confidence.${claim.confidence_label}`)
}
</script>

<template>
  <aside class="rail" :data-testid="testIds.rail" :aria-label="t('step4.reader.railTitle', { num: sectionNum ?? '' })">
    <div class="rail-block">
      <p class="rail-label">{{ t('step4.reader.railTitle', { num: sectionNum ?? '' }) }}</p>
      <div v-if="hypotheses.length" class="detail-tabs" role="tablist" aria-label="Aussagen-Ansicht">
        <button
          type="button"
          class="detail-tab"
          :class="{ 'is-active': activeDetailTab === 'claims' }"
          role="tab"
          :aria-selected="activeDetailTab === 'claims'"
          @click="activeDetailTab = 'claims'"
        >
          Claims · {{ claims.length }}
        </button>
        <button
          type="button"
          class="detail-tab"
          :class="{ 'is-active': activeDetailTab === 'hypotheses' }"
          role="tab"
          :aria-selected="activeDetailTab === 'hypotheses'"
          data-testid="hypotheses-tab"
          @click="activeDetailTab = 'hypotheses'"
        >
          Hypothesen · {{ hypotheses.length }}
        </button>
      </div>
      <template v-if="activeDetailTab === 'claims'">
        <p v-if="!claims.length" class="rail-empty">{{ t('step4.reader.railEmpty') }}</p>
        <div v-for="claim in claims" :key="claim.claim_id" class="claim" :data-testid="testIds.claim">
          <div class="claim-head">
            <span class="chip" :class="`chip--${claim.confidence_label}`">{{ confidenceWord(claim) }}</span>
            <span class="claim-id">{{ claim.claim_id }}</span>
          </div>
          <p class="claim-text">{{ claim.claim_text }}</p>
        </div>
      </template>
      <template v-else>
        <article v-for="hypothesis in hypotheses" :key="hypothesis.hypothesis_id" class="hypothesis-card">
          <div class="claim-head">
            <span class="chip chip--hyp">Hypothese</span>
            <strong class="claim-id">{{ hypothesis.hypothesis_id }}</strong>
          </div>
          <p class="claim-text">{{ hypothesis.hypothesis_text }}</p>
          <p class="hypothesis-rationale">{{ hypothesis.rationale }}</p>
          <ul v-if="hypothesis.suggested_evidence.length" class="hypothesis-evidence">
            <li v-for="item in hypothesis.suggested_evidence" :key="item">{{ item }}</li>
          </ul>
        </article>
      </template>
    </div>

    <div v-if="sectionEvidence.length" class="rail-block">
      <p class="rail-label">{{ t('step4.reader.railEvidenceTitle') }}</p>
      <div v-for="item in sectionEvidence" :key="item.evidence_id" class="evrow">
        <span class="evrow-kind">{{ item.type }}</span>
        <span class="evrow-body">
          <span>{{ item.source }}</span>
          <!-- `quote` ist optional, `snippet` Pflichtfeld (min_length=1,
               EvidenceRecordModel). Ohne Rueckfall auf snippet zeigte eine
               Evidence ohne Zitat nur ihren Quellennamen und sonst nichts. -->
          <blockquote v-if="item.quote" class="evrow-quote evidence-quote">{{ item.quote }}</blockquote>
          <p v-else-if="item.snippet" class="evrow-snippet">{{ item.snippet }}</p>
          <button
            v-if="item.source_id_anchor"
            type="button"
            class="evrow-anchor evidence-anchor-link"
            @click="emit('navigate', item.source_id_anchor as string)"
          >
            {{ t('step4.quote.openSource') }}
          </button>
        </span>
      </div>
    </div>

    <div v-if="gaps.length" class="rail-block">
      <p class="rail-label">{{ t('step4.reader.railGapsTitle') }}</p>
      <div v-for="gap in gaps" :key="gap.gap_id" class="gap" :data-testid="testIds.gap">
        <span>{{ gap.claim_text }}</span>
        <span class="gap-reason">{{ gap.gap_reason }}</span>
      </div>
    </div>

    <div v-if="redTeamFindings.length" class="rail-block rail-block--danger" :data-testid="testIds.redTeam">
      <p class="rail-label rail-label--danger">
        {{ t('step4.reader.railRedTeamTitle', { num: sectionNum ?? '' }) }}
      </p>
      <p class="rail-finding">{{ redTeamFindings[0] }}</p>
    </div>
  </aside>
</template>

<style scoped>
.rail {
  border-left: 1px solid var(--border-default);
  overflow-y: auto;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.rail-block {
  padding: var(--s-4);
  border-bottom: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.rail-block--danger {
  background: var(--status-error-soft);
  border-left: 2px solid var(--status-error);
}
.rail-label {
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: var(--text-secondary);
  margin: 0 0 4px;
}
.rail-label--danger {
  color: var(--status-error-text, var(--status-error));
}
.rail-empty {
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}
.claim {
  padding-top: var(--s-2);
  border-top: 1px solid var(--border-subtle);
}
.claim:first-of-type {
  border-top: none;
  padding-top: 0;
}
.claim-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.claim-id {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-secondary);
}
.claim-text {
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-prose);
  line-height: 1.5;
  margin: 0;
}
.chip {
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: var(--r-pill, 999px);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
  white-space: nowrap;
}
.chip--verified,
.chip--high {
  color: var(--status-success-text, var(--accent-primary));
  border-color: var(--accent-primary);
}
.chip--medium {
  color: var(--status-warning-text, var(--status-warning));
  border-color: var(--status-warning);
}
.chip--low,
.chip--speculative {
  color: var(--text-secondary);
}
.evrow {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr);
  gap: 10px;
  align-items: baseline;
  padding: 4px 0;
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--text-secondary);
}
.evrow-kind {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--accent-primary);
}
.evrow-quote {
  border-left: 2px solid var(--accent-primary);
  margin: 4px 0;
  padding: 2px 0 2px 8px;
  font-family: var(--font-serif, var(--font-sans));
  color: var(--text-prose);
}
/* Der Snippet-Rueckfall ist ein Quellenauszug, kein Zitat — deshalb ohne
   Zitatbalken und in der Fliesstext-Familie, damit die beiden im Belegrand
   auf einen Blick unterscheidbar bleiben. */
.evrow-snippet {
  margin: 4px 0;
  color: var(--text-secondary);
}
.evrow-anchor {
  appearance: none;
  background: transparent;
  border: 1px solid var(--accent-primary);
  color: var(--accent-primary);
  padding: 2px 8px;
  border-radius: var(--r-pill, 999px);
  font-size: 11px;
  cursor: pointer;
}
.gap {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 5px 0;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-secondary);
  border-top: 1px solid var(--border-subtle);
}
.gap:first-of-type {
  border-top: none;
  padding-top: 0;
}
.gap-reason {
  font-size: 11.5px;
  color: var(--status-warning-text, var(--status-warning));
}
.rail-finding {
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-prose);
  margin: 0;
  max-width: 70ch;
}
.detail-tabs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: var(--s-2);
}
.detail-tab {
  border: 1px solid var(--border-default);
  background: transparent;
  color: var(--text-secondary);
  padding: 6px 8px;
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 11px;
}
.detail-tab.is-active {
  border-color: var(--accent-primary);
  color: var(--text-primary);
}
.chip--hyp {
  color: var(--status-warning-text, var(--status-warning));
  border-color: var(--status-warning);
}
.hypothesis-card {
  padding-top: var(--s-2);
  border-top: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.hypothesis-card:first-of-type {
  border-top: none;
  padding-top: 0;
}
.hypothesis-rationale {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
}
.hypothesis-evidence {
  margin: 0.2em 0 0;
  padding-left: 1.2em;
  color: var(--text-secondary);
  font-size: 12px;
}
</style>
