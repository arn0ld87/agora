<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Button from '@/components/v4/forms/Button.vue'
import Kicker from '@/components/v4/data/Kicker.vue'
import ReportEvidencePanel from './ReportEvidencePanel.vue'
import ReportBranchControls from './ReportBranchControls.vue'
import ReportRedTeamSection from '../report/ReportRedTeamSection.vue'
import type { EvidenceIndex, ReportSection } from '../../contracts/reportContract'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  reportHtml: string
  redTeamFindings?: string[]
  evidenceSections?: ReportSection[]
  evidenceIndex?: EvidenceIndex
  selectedEvidenceSection?: number | null
  resolvedSimulationId?: string | null
  simulationId?: string
  branchBusy?: boolean
  /** Issue #1188 (Nachbesserung): true, sobald Step4Report.vue das
   *  Retry-Budget fuer die Evidenzkarte ausgeschoepft hat (Lauf terminal,
   *  Karte bleibt weg). Steuert, ob der Tooltip "wird noch erzeugt" oder
   *  "nicht verfuegbar" zeigt — Ersteres waere nach Budget-Ende eine
   *  Falschaussage an den Nutzer. */
  evidenceUnavailable?: boolean
}>(), {
  redTeamFindings: () => [],
  evidenceSections: () => [],
  evidenceIndex: () => ({}),
  selectedEvidenceSection: null,
  resolvedSimulationId: null,
  simulationId: '',
  branchBusy: false,
  evidenceUnavailable: false,
})

const emit = defineEmits([
  'update:selectedEvidenceSection',
  'navigate',
  'create-branch',
  'go-conversation',
  'copy-markdown',
  'download-markdown',
  'download-json',
  'download-html',
  'print-report',
  'download-evidence',
])

// Issue #1188: der Evidence-Export darf nicht ersatzlos verschwinden, nur
// weil die Evidenzkarte (noch) nicht vorliegt — fuer den Nutzer ist das nicht
// von einem entfernten Feature unterscheidbar. Der Button bleibt sichtbar
// und wird stattdessen deaktiviert (aria-disabled + zugaengliche Beschreibung
// via aria-describedby, nicht nur ein title-Attribut), solange keine
// Evidence-Sections vorliegen. Step4Report.vue laedt die Evidenzkarte nach
// Abschluss des Laufs erneut (mit Retry), sodass der Button aktiv wird,
// sobald die Karte eintrifft — siehe loadEvidence()/scheduleEvidenceRetry().
const evidenceReady = computed(() => (props.evidenceSections?.length ?? 0) > 0)
const evidencePendingDescKey = computed(() =>
  props.evidenceUnavailable ? 'step4.export.evidenceUnavailable' : 'step4.export.evidencePending',
)

function handleDownloadEvidence() {
  if (!evidenceReady.value) return
  emit('download-evidence')
}
</script>

<template>
  <div class="report-final-view" data-testid="report-final-view">
    <!-- Rendered final report -->
    <article class="card">
      <header class="card-head">
        <Kicker num="04" accent>Bericht</Kicker>
        <div class="log-meta">
          <Button variant="ghost" @click="emit('copy-markdown')">Markdown kopieren</Button>
          <Button variant="ghost" @click="emit('download-markdown')">.md</Button>
          <Button variant="ghost" @click="emit('download-json')">.json</Button>
          <Button variant="ghost" @click="emit('download-html')">.html</Button>
          <Button variant="ghost" @click="emit('print-report')">{{ t('step4.view.printPdf') }}</Button>
          <span class="evidence-export-wrap">
            <Button
              variant="ghost"
              :aria-disabled="!evidenceReady"
              :aria-describedby="!evidenceReady ? 'evidence-export-pending-desc' : undefined"
              :class="{ 'is-pending': !evidenceReady }"
              data-testid="download-evidence-btn"
              @click="handleDownloadEvidence"
            >
              {{ t('step4.view.evidenceJson') }}
            </Button>
            <span
              v-if="!evidenceReady"
              id="evidence-export-pending-desc"
              class="sr-only"
              data-testid="evidence-export-pending-desc"
            >
              {{ t(evidencePendingDescKey) }}
            </span>
          </span>
        </div>
      </header>
      <ReportRedTeamSection :findings="redTeamFindings ?? []" />
      <div class="report-layout" :class="{ 'report-layout--stacked': !evidenceSections.length }">
        <div class="report-body markdown-body" v-html="reportHtml"></div>
        <ReportEvidencePanel
          v-if="evidenceSections.length"
          :selected-section="selectedEvidenceSection"
          :sections="evidenceSections"
          :evidence-index="evidenceIndex"
          @update:selected-section="emit('update:selectedEvidenceSection', $event)"
          @navigate="emit('navigate', $event)"
        />
      </div>
    </article>

    <!-- Conversation hand-off -->
    <article class="card">
      <header class="card-head">
        <Kicker num="05" accent>{{ t('step4.next') }}</Kicker>
      </header>
      <ReportBranchControls
        v-if="resolvedSimulationId || simulationId"
        :branch-busy="branchBusy"
        @create="emit('create-branch', $event)"
      />
      <div class="actions">
        <Button variant="primary" arrow @click="emit('go-conversation')">{{ t('step4.next') }}</Button>
      </div>
    </article>
  </div>
</template>

<style scoped>
.report-final-view { display: flex; flex-direction: column; gap: var(--s-5); }
.card { background: var(--bg); border: 1px solid var(--rule); border-radius: var(--r-1); padding: var(--s-5); display: flex; flex-direction: column; gap: var(--s-4); }
.card-head { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--rule); padding-bottom: var(--s-3); }
.log-meta { display: flex; gap: var(--s-2); flex-wrap: wrap; }
.evidence-export-wrap { display: inline-flex; }
.evidence-export-wrap :deep(.is-pending) { opacity: 0.55; cursor: not-allowed; }
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.actions { display: flex; gap: var(--s-3); justify-content: flex-end; }
.report-body {
  max-width: 72ch;
  margin: 0 auto;
  font-family: var(--ff-sans);
  color: var(--fg);
  font-size: var(--fs-18, 17px);
  line-height: 1.75;
  padding: var(--s-4) 0;
}
.report-layout { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(300px, 0.9fr); gap: var(--s-5); }
.report-layout--stacked { grid-template-columns: 1fr; }
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) { font-family: var(--ff-sans); color: var(--fg); line-height: 1.25; margin: 1.8em 0 0.4em; font-weight: 600; letter-spacing: -0.02em; }
.markdown-body :deep(h1) { font-size: 2em; border-bottom: 1px solid var(--rule); padding-bottom: 0.3em; }
.markdown-body :deep(h2) { font-size: 1.5em; color: var(--accent); }
.markdown-body :deep(h3) { font-size: 1.2em; }
.markdown-body :deep(h4) { font-size: 1.05em; text-transform: uppercase; letter-spacing: var(--ls-mono); font-family: var(--ff-mono); color: var(--fg-muted); }
.markdown-body :deep(p) { margin: 0.9em 0; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { margin: 0.9em 0 0.9em 1.4em; padding: 0; }
.markdown-body :deep(li) { margin: 0.35em 0; }
.markdown-body :deep(li p) { margin: 0.3em 0; }
.markdown-body :deep(blockquote) { border-left: 3px solid var(--accent); margin: 1em 0; padding: 0.2em 1em; color: var(--fg-muted); }
.markdown-body :deep(code) { background: var(--bg-elevated); padding: 2px 6px; border-radius: 3px; font-family: var(--ff-mono); font-size: 0.9em; }
.markdown-body :deep(pre) { background: var(--mono-900); color: var(--mono-50); padding: 1em; overflow-x: auto; border-radius: var(--r-1); font-size: 12px; line-height: 1.5; }
.markdown-body :deep(pre code) { background: transparent; padding: 0; color: inherit; }
.markdown-body :deep(table) { border-collapse: collapse; margin: 1em 0; font-family: var(--ff-sans); font-size: 0.95em; }
.markdown-body :deep(th),
.markdown-body :deep(td) { border: 1px solid var(--rule); padding: 6px 10px; text-align: left; }
.markdown-body :deep(th) { background: var(--bg-elevated); font-weight: 500; }
.markdown-body :deep(hr) { border: 0; border-top: 1px solid var(--rule); margin: 2em 0; }
.markdown-body :deep(a) { color: var(--accent); text-decoration: underline; text-underline-offset: 2px; }
.markdown-body :deep(strong) { font-weight: 600; color: var(--fg); }
@media (max-width: 880px) { .report-layout { grid-template-columns: 1fr; } }
</style>
