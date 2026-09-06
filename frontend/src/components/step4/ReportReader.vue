<script setup lang="ts">
/**
 * ReportReader — Leseumgebung fuer den abgeschlossenen Bericht (PR 6,
 * Premium-Redesign 2026-09, "Bericht lesen").
 *
 * Ersetzt die vormalige Formular-Stack-Optik (Audit Problem #4) durch drei
 * Spalten: Outline links (ReportOutline.vue), Serif-Lesespalte in der Mitte
 * (62ch, Newsreader), Belegrand rechts (ReportEvidenceRail.vue). Modell und
 * Modus fuer eine Regenerierung wandern in ein Overlay statt in ein
 * dauerhaft sichtbares Formular ueber dem Bericht.
 */
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ReportReaderTestId } from '@/contracts/testIds'
import Button from '@/components/v4/forms/Button.vue'
import ReportOutline from './ReportOutline.vue'
import type { ReportOutlineItem } from './ReportOutline.vue'
import ReportEvidenceRail from './ReportEvidenceRail.vue'
import ReportModelControls from './ReportModelControls.vue'
import ReportModeControls from './ReportModeControls.vue'
import ReportBranchControls from './ReportBranchControls.vue'
import ReportRedTeamSection from '../report/ReportRedTeamSection.vue'
import type { EvidenceIndex, ReportOutline as ReportOutlineData, ReportSection } from '../../contracts/reportContract'
import type { AiModelRef } from '../../contracts/aiModelRef'
import type { ReportMode } from '../../contracts/reportV3Contract'

const props = withDefaults(
  defineProps<{
    outline: ReportOutlineData
    sectionHtml: Record<string, string>
    evidenceSections?: ReportSection[]
    evidenceIndex?: EvidenceIndex
    redTeamFindings?: string[]
    evidenceUnavailable?: boolean
    reportRoute: AiModelRef | null
    reportMode: ReportMode
    isRegenerating?: boolean
    resolvedSimulationId?: string | null
    simulationId?: string
    branchBusy?: boolean
  }>(),
  {
    evidenceSections: () => [],
    evidenceIndex: () => ({}),
    redTeamFindings: () => [],
    evidenceUnavailable: false,
    isRegenerating: false,
    resolvedSimulationId: null,
    simulationId: '',
    branchBusy: false,
  },
)

const emit = defineEmits<{
  'update:reportRoute': [value: AiModelRef | null]
  'update:reportMode': [value: ReportMode]
  regenerate: []
  navigate: [anchor: string]
  'create-branch': [branchForm: { branch_name: string; llm_model: string; language: string; max_agents: string }]
  'go-conversation': []
  'copy-markdown': []
  'download-markdown': []
  'download-json': []
  'download-html': []
  'print-report': []
  'download-evidence': []
}>()

const { t } = useI18n()
const testIds = ReportReaderTestId

const activeId = ref('summary')
// Ob der Nutzer die Outline bereits selbst bedient hat. Solange nicht,
// darf ein verspaetet eintreffender Evidence-Load (Retry-Backoff, siehe
// Step4Report.vue::loadEvidence) die aktive Section noch auf die erste
// Evidence-Section vorbelegen — spiegelt die vormalige Auswahl in
// loadEvidence() ("erste Section automatisch ausgewaehlt"). Sobald der
// Nutzer navigiert hat, gewinnt seine Wahl gegen jeden Nachlade-Effekt.
const userNavigated = ref(false)
watch(
  () => props.evidenceSections,
  (sections) => {
    if (userNavigated.value || !sections.length) return
    activeId.value = `section-${sections[0].section_index}`
  },
  { immediate: true },
)

const railOpen = ref(true)
const overlayOpen = ref(false)
const regenerateOpenBtnRef = ref<InstanceType<typeof Button> | null>(null)
const regenerateCloseBtnRef = ref<InstanceType<typeof Button> | null>(null)

const outlineItems = computed<ReportOutlineItem[]>(() => [
  { id: 'summary', num: '0', label: t('step4.reader.outlineSummary') },
  ...props.outline.sections.map((section, idx) => ({
    id: `section-${idx + 1}`,
    num: String(idx + 1),
    label: section.title,
  })),
])

// Der Anhangszaehler muss den Ueberhang mitzaehlen: `hypotheses` ist auf fuenf
// gedeckelt, der Rest steht in `hypotheses_appendix` (ReportSectionModel).
const hypothesesCount = computed(() =>
  props.evidenceSections.reduce(
    (total, section) => total + section.hypotheses.length + (section.hypotheses_appendix?.length ?? 0),
    0,
  ),
)

const evidenceReady = computed(() => (props.evidenceSections?.length ?? 0) > 0)
const evidencePendingDescKey = computed(() =>
  props.evidenceUnavailable ? 'step4.export.evidenceUnavailable' : 'step4.export.evidencePending',
)

const activeSectionNum = computed<number | null>(() => {
  const match = /^section-(\d+)$/.exec(activeId.value)
  return match ? Number(match[1]) : null
})

const activeEvidenceSection = computed<ReportSection | null>(() => {
  const num = activeSectionNum.value
  if (num === null) return null
  return props.evidenceSections.find((section) => section.section_index === num) ?? null
})

function navigateToSection(id: string) {
  userNavigated.value = true
  activeId.value = id
  const target = document.getElementById(id)
  target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function handleDownloadEvidence() {
  if (!evidenceReady.value) return
  emit('download-evidence')
}

async function openOverlay() {
  overlayOpen.value = true
  await nextTick()
  const el = (regenerateCloseBtnRef.value as unknown as { $el?: HTMLElement })?.$el
  el?.focus()
}

async function closeOverlay() {
  overlayOpen.value = false
  await nextTick()
  const el = (regenerateOpenBtnRef.value as unknown as { $el?: HTMLElement })?.$el
  el?.focus()
}

function confirmRegenerate() {
  emit('regenerate')
  void closeOverlay()
}

function onOverlayKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    void closeOverlay()
  }
}

watch(
  () => props.outline,
  () => {
    activeId.value = 'summary'
    userNavigated.value = false
  },
)
</script>

<template>
  <div class="reader" :data-testid="testIds.root">
    <header class="reader-header">
      <div class="reader-header-actions">
        <Button
          ref="regenerateOpenBtnRef"
          variant="secondary"
          size="sm"
          :disabled="isRegenerating"
          :data-testid="testIds.regenerateOpen"
          @click="openOverlay"
        >
          {{ t('step4.reader.regenerate.openButton') }}
        </Button>
        <Button variant="ghost" size="sm" :data-testid="testIds.railToggle" @click="railOpen = !railOpen">
          {{ railOpen ? t('step4.reader.railToggleHide') : t('step4.reader.railToggleShow') }}
        </Button>
        <Button variant="ghost" size="sm" @click="emit('copy-markdown')">Markdown kopieren</Button>
        <Button variant="ghost" size="sm" @click="emit('download-markdown')">.md</Button>
        <Button variant="ghost" size="sm" @click="emit('download-json')">.json</Button>
        <Button variant="ghost" size="sm" @click="emit('download-html')">.html</Button>
        <Button variant="ghost" size="sm" @click="emit('print-report')">{{ t('step4.view.printPdf') }}</Button>
        <span class="evidence-export-wrap">
          <Button
            variant="ghost"
            size="sm"
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
        <Button variant="primary" size="sm" arrow @click="emit('go-conversation')">{{ t('step4.next') }}</Button>
      </div>
    </header>

    <div class="reader-body" :class="{ 'reader-body--no-rail': !railOpen }">
      <ReportOutline
        :items="outlineItems"
        :active-id="activeId"
        :sections-count="outline.sections.length"
        :hypotheses-count="hypothesesCount"
        :data-gaps-count="evidenceSections.reduce((n, s) => n + s.data_gaps.length, 0)"
        :evidence-count="Object.keys(evidenceIndex).length"
        :red-team-count="redTeamFindings.length"
        @navigate="navigateToSection"
      />

      <article class="body" :data-testid="testIds.body">
        <ReportRedTeamSection :findings="redTeamFindings" />
        <section id="summary" class="report-section">
          <p class="section-kicker">{{ t('step4.reader.outlineSummary') }}</p>
          <h1 class="report-title">{{ outline.title }}</h1>
          <p class="prose">{{ outline.summary }}</p>
        </section>
        <section
          v-for="(section, idx) in outline.sections"
          :id="`section-${idx + 1}`"
          :key="idx"
          class="report-section"
          :data-testid="testIds.section"
        >
          <p class="section-kicker">{{ t('step4.reader.outlineSection', { num: idx + 1 }) }}</p>
          <h2 class="report-heading">{{ section.title }}</h2>
          <div class="prose markdown-body" v-html="sectionHtml[idx + 1] || ''"></div>
        </section>
      </article>

      <ReportEvidenceRail
        v-if="railOpen"
        :section="activeEvidenceSection"
        :section-num="activeSectionNum"
        :evidence-index="evidenceIndex"
        :red-team-findings="redTeamFindings"
        @navigate="emit('navigate', $event)"
      />
    </div>

    <footer class="reader-footer">
      <ReportBranchControls
        v-if="resolvedSimulationId || simulationId"
        :branch-busy="branchBusy"
        @create="emit('create-branch', $event)"
      />
    </footer>

    <div
      v-if="overlayOpen"
      class="overlay-backdrop"
      :data-testid="testIds.regenerateOverlay"
      @keydown="onOverlayKeydown"
    >
      <div class="overlay-panel" role="dialog" aria-modal="true" aria-labelledby="regenerate-overlay-title">
        <header class="overlay-head">
          <h2 id="regenerate-overlay-title" class="overlay-title">{{ t('step4.reader.regenerate.title') }}</h2>
          <button
            ref="regenerateCloseBtnRef"
            type="button"
            class="overlay-close"
            :aria-label="t('step4.reader.regenerate.cancelButton')"
            :data-testid="testIds.regenerateClose"
            @click="closeOverlay"
          >
            ×
          </button>
        </header>
        <p class="overlay-desc">{{ t('step4.reader.regenerate.description') }}</p>
        <ReportModelControls
          :model-value="reportRoute"
          :is-regenerating="isRegenerating"
          @update:model-value="emit('update:reportRoute', $event)"
          @regenerate="confirmRegenerate"
        />
        <ReportModeControls
          :model-value="reportMode"
          :disabled="isRegenerating"
          @update:model-value="emit('update:reportMode', $event)"
        />
        <div class="overlay-actions">
          <Button variant="ghost" @click="closeOverlay">{{ t('step4.reader.regenerate.cancelButton') }}</Button>
          <Button
            variant="primary"
            :loading="isRegenerating"
            :disabled="isRegenerating"
            :data-testid="testIds.regenerateConfirm"
            @click="confirmRegenerate"
          >
            {{ t('step4.reader.regenerate.confirmButton') }}
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.reader {
  display: flex;
  flex-direction: column;
  gap: 0;
  border: 1px solid var(--border-default);
  border-radius: var(--r-5);
  overflow: hidden;
  background: var(--surface-base, var(--bg));
}
.reader-header {
  border-bottom: 1px solid var(--border-default);
  padding: var(--s-3) var(--s-4);
}
.reader-header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
  align-items: center;
}
.evidence-export-wrap {
  display: inline-flex;
}
.evidence-export-wrap :deep(.is-pending) {
  opacity: 0.55;
  cursor: not-allowed;
}
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
.reader-body {
  display: grid;
  grid-template-columns: 236px minmax(0, 1fr) 336px;
  min-height: 0;
}
.reader-body--no-rail {
  grid-template-columns: 236px minmax(0, 1fr);
}
.body {
  min-width: 0;
  overflow-y: auto;
  padding: var(--s-6) var(--s-8) var(--s-8);
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
}
.report-section {
  max-width: 62ch;
}
.section-kicker {
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: var(--accent-primary);
  margin: 0 0 8px;
}
.report-title {
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: var(--fs-display, 28px);
  line-height: var(--lh-display, 1.15);
  color: var(--text-primary);
  margin: 0 0 var(--s-4);
  max-width: 34ch;
}
.report-heading {
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 24px;
  line-height: 1.3;
  color: var(--text-primary);
  margin: 0 0 var(--s-4);
}
.prose {
  font-family: var(--font-serif);
  font-size: var(--fs-prose, 17px);
  line-height: var(--lh-prose, 1.6);
  color: var(--text-prose);
  margin: 0;
}
.markdown-body :deep(p) {
  margin: 0.9em 0;
}
.markdown-body :deep(blockquote) {
  border-left: 2px solid var(--accent-primary);
  margin: var(--s-4) 0 0;
  padding: 0 0 0 18px;
  max-width: 60ch;
  font-style: italic;
}
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0.9em 0 0.9em 1.4em;
  padding: 0;
}
.reader-footer {
  border-top: 1px solid var(--border-default);
  padding: var(--s-4);
}
.overlay-backdrop {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, black 55%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 60;
}
.overlay-panel {
  background: var(--surface-elevated, var(--bg));
  border: 1px solid var(--border-default);
  border-radius: var(--r-5);
  padding: var(--s-5);
  width: min(480px, 92vw);
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.overlay-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.overlay-title {
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 18px;
  color: var(--text-primary);
  margin: 0;
}
.overlay-close {
  appearance: none;
  background: transparent;
  border: none;
  font-size: 20px;
  line-height: 1;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px 8px;
}
.overlay-close:focus-visible {
  outline: var(--v4-state-focus-ring-width, 2px) solid var(--v4-state-focus-ring, var(--accent-primary));
  outline-offset: 1px;
}
.overlay-desc {
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}
.overlay-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--s-3);
  margin-top: var(--s-2);
}
@media (max-width: 1279px) {
  .reader-body {
    grid-template-columns: 220px minmax(0, 1fr) 300px;
  }
  .reader-body--no-rail {
    grid-template-columns: 220px minmax(0, 1fr);
  }
}
@media (max-width: 880px) {
  .reader-body,
  .reader-body--no-rail {
    grid-template-columns: 1fr;
  }
}
</style>
