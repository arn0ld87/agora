<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Badge from '../ui/Badge.vue'
import type { EvidenceIndex, EvidenceRecord, ReportClaim, ReportSection } from '../../contracts/reportContract'

interface Props {
  sections: ReportSection[]
  evidenceIndex?: EvidenceIndex
  selectedSection: number | null
}

const props = withDefaults(defineProps<Props>(), {
  evidenceIndex: () => ({}),
})

const emit = defineEmits<{
  'update:selectedSection': [sectionIndex: number]
  navigate: [anchor: string]
}>()

const { t } = useI18n()
const activeDetailTab = ref<'claims' | 'hypotheses'>('claims')

const activeEvidenceSection = computed(() => {
  return props.sections.find((section) => section.section_index === props.selectedSection) || null
})

const activeHypotheses = computed(() => sectionHypotheses(activeEvidenceSection.value))
const activeHypothesesAppendix = computed(() => sectionHypothesesAppendix(activeEvidenceSection.value))
const activeClaims = computed(() => activeEvidenceSection.value?.claims ?? [])

watch(activeEvidenceSection, () => {
  activeDetailTab.value = 'claims'
})

watch(activeHypotheses, (hypotheses) => {
  if (activeDetailTab.value === 'hypotheses' && hypotheses.length === 0) {
    activeDetailTab.value = 'claims'
  }
})

function claimConfidenceScore(claim: ReportClaim | null | undefined): number | null {
  return claim?.confidence_score ?? null
}

function claimConfidenceLabel(claim: ReportClaim | null | undefined): string {
  return claim?.confidence_label ?? 'low'
}

function claimConfidenceText(claim: ReportClaim | null | undefined): string {
  const label = claimConfidenceLabel(claim)
  const score = claimConfidenceScore(claim)
  return score === null ? label : `${Math.round(score * 100)}% · ${label}`
}

function claimEvidenceItems(claim: ReportClaim | null | undefined): EvidenceRecord[] {
  if (!Array.isArray(claim?.evidence)) return []
  return claim.evidence
    .map((binding) => props.evidenceIndex[binding.evidence_id])
    .filter((record): record is EvidenceRecord => record !== undefined)
}

function evidenceSnippet(item: EvidenceRecord | null | undefined): string {
  return item?.snippet ?? ''
}

function sectionHypotheses(section: ReportSection | null | undefined) {
  return Array.isArray(section?.hypotheses) ? section.hypotheses : []
}

function sectionHypothesesAppendix(section: ReportSection | null | undefined) {
  return Array.isArray(section?.hypotheses_appendix) ? section.hypotheses_appendix : []
}
</script>

<template>
  <aside class="evidence-panel">
    <div class="evidence-head">
      <strong>Evidence Inspector</strong>
      <span>{{ sections.length }} sections</span>
    </div>
    <div class="evidence-sections">
      <button
        v-for="section in sections"
        :key="section.section_index"
        class="evidence-tab"
        :class="{ active: selectedSection === section.section_index }"
        @click="emit('update:selectedSection', section.section_index)"
      >
        {{ section.section_index }} · {{ section.section_title }}
      </button>
    </div>
    <div v-if="activeEvidenceSection" class="evidence-body">
      <p class="meta">{{ activeEvidenceSection.section_summary }}</p>
      <div class="evidence-detail-tabs" role="tablist" aria-label="Evidence-Ansicht">
        <button
          type="button"
          class="evidence-detail-tab"
          :class="{ active: activeDetailTab === 'claims' }"
          @click="activeDetailTab = 'claims'"
        >
          Claims · {{ activeClaims.length }}
        </button>
        <button
          v-if="activeHypotheses.length"
          type="button"
          class="evidence-detail-tab"
          :class="{ active: activeDetailTab === 'hypotheses' }"
          data-testid="hypotheses-tab"
          @click="activeDetailTab = 'hypotheses'"
        >
          Hypothesen · {{ activeHypotheses.length }}
        </button>
      </div>
      <section
        v-if="activeDetailTab === 'hypotheses'"
        class="hypothesis-list"
        aria-label="Hypothesen ohne Evidence"
      >
        <h3>Hypothesen ohne Evidence</h3>
        <article
          v-for="hypothesis in activeHypotheses"
          :key="hypothesis.hypothesis_id"
          class="hypothesis-card"
        >
          <header>
            <strong>{{ hypothesis.hypothesis_id }}</strong>
            <Badge variant="ghost">hypothesis</Badge>
          </header>
          <p>{{ hypothesis.hypothesis_text }}</p>
          <small>{{ hypothesis.rationale }}</small>
          <ul v-if="hypothesis.suggested_evidence.length" class="hypothesis-evidence">
            <li
              v-for="item in hypothesis.suggested_evidence"
              :key="`${hypothesis.hypothesis_id}-${item}`"
            >
              {{ item }}
            </li>
          </ul>
        </article>
        <details
          v-if="activeHypothesesAppendix.length"
          class="hypothesis-appendix"
          data-testid="hypothesis-appendix"
        >
          <summary class="hypothesis-appendix-summary">
            Weitere Hypothesen ({{ activeHypothesesAppendix.length }})
          </summary>
          <ul class="hypothesis-appendix-list">
            <li
              v-for="h in activeHypothesesAppendix"
              :key="h.hypothesis_id"
              class="hypothesis-appendix-item"
            >
              <strong>{{ h.hypothesis_id }}</strong>
              <p>{{ h.hypothesis_text }}</p>
              <small v-if="h.rationale">{{ h.rationale }}</small>
            </li>
          </ul>
        </details>
      </section>
      <div v-else class="claim-list">
        <article
          v-for="claim in activeClaims"
          :key="claim.claim_id"
          class="claim-card"
        >
          <header>
            <strong>{{ claim.claim_id }}</strong>
            <Badge :variant="claimConfidenceLabel(claim) === 'speculative' || claimConfidenceLabel(claim) === 'low' ? 'ghost' : claimConfidenceLabel(claim) === 'medium' ? 'accent' : 'solid'">
              {{ claimConfidenceText(claim) }}
            </Badge>
          </header>
          <p>{{ claim.claim_text }}</p>
          <div class="evidence-items">
            <div
              v-for="(item, idx) in claimEvidenceItems(claim)"
              :key="`${claim.claim_id}-${idx}`"
              class="evidence-item"
            >
              <div class="evidence-item-head">
                <Badge variant="ghost">{{ item.type }}</Badge>
                <span v-if="item.source">{{ item.source }}</span>
              </div>
              <blockquote v-if="item.quote" class="evidence-quote">{{ item.quote }}</blockquote>
              <span v-else>{{ evidenceSnippet(item) }}</span>
              <button
                v-if="item.source_id_anchor"
                type="button"
                class="evidence-anchor-link"
                @click="emit('navigate', item.source_id_anchor)"
              >
                {{ t('step4.quote.openSource') }}
              </button>
            </div>
          </div>
        </article>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.evidence-panel {
  border-left: 1px solid var(--rule);
  padding-left: var(--s-4);
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.evidence-head {
  display: flex;
  justify-content: space-between;
  gap: var(--s-2);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
}
.evidence-sections {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.evidence-tab {
  border: 1px solid var(--rule);
  background: var(--bg);
  color: var(--fg);
  text-align: left;
  padding: 10px 12px;
  cursor: pointer;
}
.evidence-tab.active {
  border-color: var(--accent);
  background: var(--bg-elevated);
}
.evidence-detail-tabs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.evidence-detail-tab {
  border: 1px solid var(--rule);
  background: var(--bg);
  color: var(--fg-muted);
  padding: 8px 10px;
  cursor: pointer;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
}
.evidence-detail-tab.active {
  border-color: var(--accent);
  background: var(--bg-elevated);
  color: var(--fg);
}
.claim-list {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.claim-card {
  border-top: 1px solid var(--rule);
  padding-top: var(--s-3);
}
.claim-card header,
.hypothesis-card header {
  display: flex;
  justify-content: space-between;
  gap: var(--s-3);
  align-items: center;
}
.hypothesis-list {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  border-top: 1px solid var(--rule);
  padding-top: var(--s-3);
}
.hypothesis-list h3 {
  margin: 0;
  color: var(--fg-muted);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
}
.hypothesis-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  background: color-mix(in srgb, var(--status-warn, #b7791f) 8%, var(--bg-elevated));
  border: 1px solid var(--rule);
}
.hypothesis-card p {
  margin: 0;
}
.hypothesis-card small {
  color: var(--fg-muted);
  line-height: 1.5;
}
.hypothesis-evidence {
  margin: 0.2em 0 0;
  padding-left: 1.2em;
  color: var(--fg-muted);
}
.hypothesis-appendix {
  border: 1px solid var(--rule);
  margin-top: var(--s-2);
}
.hypothesis-appendix-summary {
  padding: 8px 12px;
  cursor: pointer;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  list-style: none;
}
.hypothesis-appendix-summary::-webkit-details-marker {
  display: none;
}
.hypothesis-appendix-summary::before {
  content: '+ ';
}
details[open] .hypothesis-appendix-summary::before {
  content: '- ';
}
.hypothesis-appendix-summary:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.hypothesis-appendix-list {
  list-style: none;
  margin: 0;
  padding: 0 12px 12px;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.hypothesis-appendix-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  background: color-mix(in srgb, var(--status-warn, #b7791f) 5%, var(--bg-elevated));
  border: 1px solid var(--rule);
}
.hypothesis-appendix-item p {
  margin: 0;
}
.hypothesis-appendix-item small {
  color: var(--fg-muted);
  line-height: 1.5;
}
.evidence-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: var(--s-3);
}
.evidence-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  background: var(--bg-elevated);
  border: 1px solid var(--rule);
}
.evidence-item-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--s-2);
  color: var(--fg-muted);
  font-family: var(--ff-mono);
  font-size: 11px;
}
.evidence-quote {
  border-left: 3px solid var(--accent);
  margin: 0.5em 0;
  padding: 0.4em 0.8em;
  background: var(--bg-glass);
  color: var(--fg-meta);
  font-size: 0.92em;
}
.evidence-anchor-link {
  appearance: none;
  background: transparent;
  border: 1px solid var(--accent);
  color: var(--accent);
  padding: 0.2em 0.6em;
  border-radius: var(--r-pill);
  font-size: 0.85em;
  cursor: pointer;
  margin-left: 0.4em;
}
.evidence-anchor-link:hover {
  background: var(--accent-soft);
}
@media (max-width: 880px) {
  .evidence-panel {
    border-left: 0;
    border-top: 1px solid var(--rule);
    padding-left: 0;
    padding-top: var(--s-4);
  }
}
</style>
