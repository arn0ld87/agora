<script setup lang="ts">
/**
 * Lesetext (Mitte) des Bericht-Reiters (Etappe 5, #1804, Bauplan 4.6).
 *
 * Schnittstelle für andere Tickets:
 *   Prop   `activeSection: number | null`  Abschnitt, zu dem gescrollt wird (`?section=`)
 *   Daten  `useRunReportContext()`         `reading` (Abschnitte mit sanitisiertem HTML),
 *                                          `report`, `generation`
 *   Anker  jeder Abschnitt hat `id="report-section-<n>"` und `data-section="<n>"`
 *   Slot   `section-after` (Prop `section`) hinter dem Text eines Abschnitts
 *
 * Der Text kommt aus `renderMarkdown` (marked + DOMPurify), derselben Funktion
 * wie im Bestand (`Step4Report`); es gibt kein unsanitisiertes `v-html`.
 * Während der Erzeugung zeigt die Mitte Fortschritt und die schon fertigen
 * Abschnitte; das Protokoll liegt in einem einklappbaren Bereich.
 */
import { computed, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ReportLiveLogPane from '@/components/step4/ReportLiveLogPane.vue'
import { useRunReportContext } from '@/composables/run/report/useRunReport'
import type { ReadingSection } from '@/composables/run/report/reportSections'

const props = defineProps<{ activeSection: number | null }>()
const { t } = useI18n()
const ctx = useRunReportContext()

const RUNNING = new Set(['pending', 'planning', 'generating'])

const reportData = computed(() => (ctx.report.value.status === 'ok' ? ctx.report.value.report : null))
const gen = ctx.generation
const running = computed(
  () => (reportData.value ? RUNNING.has(reportData.value.status) : false) || gen.status.phase.value === 1,
)
const startOffered = computed(
  () => ctx.report.value.status === 'idle' && gen.status.pending.value && !gen.status.isComplete.value,
)
const failureReason = computed<string | null>(() => {
  if (reportData.value?.status === 'failed') return reportData.value.error || t('views.run.report.reading.failedUnknown')
  if (gen.status.backendStatus.value === 'failed') {
    return gen.report.lastStatus.value?.error || t('views.run.report.reading.failedUnknown')
  }
  return null
})
const sectionsTotal = computed(() => ctx.reading.value.sections.length)
const sectionsDone = computed(() => ctx.reading.value.sections.filter((s) => s.state === 'ready').length)
const hasText = computed(() => {
  const r = ctx.reading.value
  return r.mode === 'whole' ? r.wholeHtml.length > 0 : r.sections.some((s) => s.html.length > 0)
})

function stateNote(section: ReadingSection): string | null {
  if (section.state === 'ready') return null
  return t(`views.run.report.reading.sectionNote.${section.state}`)
}

watch(
  () => props.activeSection,
  async (n) => {
    if (n === null) return
    await nextTick()
    const el = document.getElementById(`report-section-${n}`)
    if (el && typeof el.scrollIntoView === 'function') el.scrollIntoView({ block: 'start' })
  },
  { flush: 'post' },
)
</script>

<template>
  <div class="rr-read" data-testid="report-reading">
    <p v-if="ctx.report.value.status === 'loading'" class="rr-read__note" role="status" data-testid="report-loading">
      {{ t('views.run.report.reading.loading') }}
    </p>

    <section v-else-if="ctx.report.value.status === 'failed'" class="rr-read__problem" role="alert" data-testid="report-load-failed">
      <p class="rr-read__problem-title">
        {{ t(`views.run.report.reading.loadFailed.${ctx.report.value.kind}`) }}
      </p>
      <p class="rr-read__detail">{{ ctx.report.value.reason }}</p>
      <button type="button" class="rr-read__btn" data-testid="report-retry" @click="ctx.reloadSelected()">
        {{ t('views.run.report.reading.retry') }}
      </button>
    </section>

    <section v-if="startOffered" class="rr-read__start" data-testid="report-start">
      <p class="rr-read__problem-title">{{ t('views.run.report.generation.startTitle') }}</p>
      <p class="rr-read__detail">{{ t('views.run.report.generation.startDescription') }}</p>
      <button
        type="button"
        class="rr-read__btn rr-read__btn--primary"
        :disabled="gen.status.isBusy.value"
        data-testid="report-start-button"
        @click="gen.start()"
      >
        {{ t('views.run.report.generation.startButton') }}
      </button>
    </section>

    <section v-if="running" class="rr-read__progress" data-testid="report-progress">
      <p class="rr-read__progress-title" role="status">
        {{ t('views.run.report.generation.running') }}
        <span v-if="sectionsTotal > 0">
          · {{ t('views.run.report.generation.sectionsDone', { done: sectionsDone, total: sectionsTotal }) }}
        </span>
      </p>
      <p v-if="gen.status.message.value" class="rr-read__detail" data-testid="report-progress-message">{{ gen.status.message.value }}</p>
      <p v-if="gen.status.transportError.value" class="rr-read__warn" role="alert" data-testid="report-transport-error">
        {{ t('views.run.report.generation.transportError') }}
      </p>
    </section>

    <p v-if="failureReason" class="rr-read__problem" role="alert" data-testid="report-failed">
      <strong>{{ t('views.run.report.generation.failed') }}</strong> {{ failureReason }}
    </p>
    <p v-if="gen.notice.value && !failureReason" class="rr-read__warn" role="alert" data-testid="report-notice">
      {{ gen.notice.value }}
    </p>
    <section v-if="ctx.schemaError.value" class="rr-read__problem" role="alert" data-testid="report-schema-error">
      <p class="rr-read__problem-title">{{ t('views.run.report.generation.schemaError', { where: ctx.schemaError.value.where }) }}</p>
      <ul>
        <li v-for="issue in ctx.schemaError.value.issues" :key="issue">{{ issue }}</li>
      </ul>
    </section>

    <article v-if="reportData || running" class="rr-read__text" data-testid="report-text">
      <header v-if="ctx.reading.value.title" class="rr-read__titles">
        <p class="rr-read__title" data-testid="report-title">{{ ctx.reading.value.title }}</p>
        <p v-if="ctx.reading.value.summary" class="rr-read__summary">{{ ctx.reading.value.summary }}</p>
      </header>

      <template v-if="ctx.reading.value.mode === 'sections'">
        <section
          v-for="section in ctx.reading.value.sections"
          :id="`report-section-${section.index}`"
          :key="section.index"
          class="rr-read__section"
          :data-section="section.index"
          :data-state="section.state"
          data-testid="report-section"
        >
          <p class="rr-read__kicker">{{ t('views.run.report.reading.sectionKicker', { n: section.index }) }}</p>
          <h3 class="rr-read__heading">{{ section.title }}</h3>
          <p v-if="stateNote(section)" class="rr-read__section-note" data-testid="report-section-note">
            {{ stateNote(section) }}
          </p>
          <div v-if="section.html" class="rr-read__prose" v-html="section.html" />
          <slot name="section-after" :section="section" />
        </section>
      </template>
      <template v-else>
        <!-- Gespeicherter Bericht ohne Text je Abschnitt: ein Block; die Gliederung nennt die Zustände. -->
        <section id="report-section-1" class="rr-read__section" data-section="1" data-testid="report-whole">
          <div v-if="ctx.reading.value.wholeHtml" class="rr-read__prose" v-html="ctx.reading.value.wholeHtml" />
          <p v-else-if="!running" class="rr-read__note" data-testid="report-empty-text">
            {{ t('views.run.report.reading.emptyText') }}
          </p>
        </section>
      </template>
      <p v-if="running && !hasText" class="rr-read__note">{{ t('views.run.report.generation.noSectionsYet') }}</p>
    </article>

    <details v-if="running || gen.agentLogs.value.length > 0 || gen.consoleLogs.value.length > 0" class="rr-read__log" data-testid="report-log">
      <summary class="rr-read__log-summary">{{ t('views.run.report.generation.logToggle') }}</summary>
      <ReportLiveLogPane :agent-logs="gen.agentLogs.value" :console-logs="gen.consoleLogs.value" />
    </details>
  </div>
</template>

<style scoped>
.rr-read {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}
.rr-read__text {
  max-width: 68ch;
  font-family: var(--font-serif);
  color: var(--fg);
}
.rr-read__titles {
  margin-bottom: 18px;
}
.rr-read__title {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 650;
  line-height: 1.3;
}
.rr-read__summary {
  margin: 0;
  color: var(--fg2);
  line-height: 1.6;
}
.rr-read__section {
  margin-bottom: 22px;
  scroll-margin-top: 12px;
}
.rr-read__kicker {
  margin: 0;
  font-family: var(--font-sans);
  font-size: 12px;
  font-weight: 600;
  color: var(--fg3);
}
.rr-read__heading {
  margin: 2px 0 8px;
  font-size: 17px;
  font-weight: 650;
}
.rr-read__section-note {
  margin: 0 0 8px;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 600;
  color: var(--warn);
}
.rr-read__section[data-state='failed'] .rr-read__section-note {
  color: var(--err);
}
.rr-read__prose {
  font-size: 16px;
  line-height: 1.7;
}
.rr-read__note,
.rr-read__detail {
  margin: 0;
  font-size: 13px;
  color: var(--fg2);
}
.rr-read__warn {
  margin: 0;
  font-size: 13px;
  color: var(--warn);
}
.rr-read__problem,
.rr-read__start,
.rr-read__progress {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-12);
  background: var(--s2);
  font-size: 13px;
}
.rr-read__problem {
  border-color: var(--err);
}
.rr-read__problem-title,
.rr-read__progress-title {
  margin: 0;
  font-weight: 650;
}
.rr-read__btn {
  align-self: flex-start;
  height: 32px;
  padding: 0 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.rr-read__btn--primary {
  background: var(--acc);
  border-color: var(--acc);
  color: var(--on-acc);
}
.rr-read__btn:disabled {
  color: var(--fg3);
  cursor: not-allowed;
}
.rr-read__btn:focus-visible,
.rr-read__log-summary:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.rr-read__log-summary {
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: var(--fg2);
}
</style>
