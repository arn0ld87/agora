<script setup lang="ts">
/**
 * Seitenspalte (rechts) des Bericht-Reiters (Etappe 5, #1804, Bauplan 4.6):
 * Umschalter „Belege | Nachfragen“ als Tabs (ARIA, Pfeiltasten, Pos1/Ende).
 *
 * Schnittstelle für andere Tickets:
 *   Prop   `panel: 'evidence' | 'questions'`   sichtbarer Bereich (`?panel=`)
 *   Emit   `update:panel(value)`               Umschalter betätigt
 *   Slots  `evidence`   Inhalt „Belege“ (Platzhalter bis zum Ticket „Belegspalte“)
 *          `questions`  Inhalt „Nachfragen“ (Platzhalter bis zum Ticket „Nachfragen“)
 *   Daten  `useRunReportContext()`  `evidence` (ok | omitted | failed | loading),
 *          `selectedClaimId`
 *
 * Bei `evidence_omitted` steht im Bereich „Belege“ ein eigener, deutlich
 * sichtbarer Hinweis, nie eine Formulierung wie „Datenlücke“: die Belege
 * existieren, ließen sich aber nicht vertragskonform ausliefern. Der Hinweis
 * steht über dem Slot und bleibt, auch wenn ein anderes Ticket den Slot füllt.
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRunReportContext } from '@/composables/run/report/useRunReport'

export type SidePanel = 'evidence' | 'questions'
const PANELS: readonly SidePanel[] = ['evidence', 'questions']

const props = defineProps<{ panel: SidePanel }>()
const emit = defineEmits<{ 'update:panel': [value: SidePanel] }>()
const { t } = useI18n()
const ctx = useRunReportContext()

const tabRefs = ref<Partial<Record<SidePanel, HTMLElement | null>>>({})

function setTab(el: unknown, key: SidePanel): void {
  tabRefs.value[key] = el instanceof HTMLElement ? el : null
}

function pick(next: SidePanel, focus = false): void {
  if (next !== props.panel) emit('update:panel', next)
  if (focus) tabRefs.value[next]?.focus()
}

function onKey(event: KeyboardEvent): void {
  const i = PANELS.indexOf(props.panel)
  let next: SidePanel | null = null
  if (event.key === 'ArrowRight') next = PANELS[(i + 1) % PANELS.length]!
  else if (event.key === 'ArrowLeft') next = PANELS[(i - 1 + PANELS.length) % PANELS.length]!
  else if (event.key === 'Home') next = PANELS[0]!
  else if (event.key === 'End') next = PANELS[PANELS.length - 1]!
  if (!next) return
  event.preventDefault()
  pick(next, true)
}
</script>

<template>
  <aside class="rr-side" :aria-label="t('views.run.report.side.label')" data-testid="report-side">
    <div class="rr-side__tabs" role="tablist" :aria-label="t('views.run.report.side.tabsLabel')" @keydown="onKey">
      <button
        v-for="key in PANELS"
        :id="`report-side-tab-${key}`"
        :key="key"
        :ref="(el) => setTab(el, key)"
        type="button"
        role="tab"
        class="rr-side__tab"
        :aria-selected="panel === key"
        :aria-controls="`report-side-panel-${key}`"
        :tabindex="panel === key ? 0 : -1"
        :data-testid="`report-side-tab-${key}`"
        @click="pick(key)"
      >
        {{ t(`views.run.report.side.tab.${key}`) }}
      </button>
    </div>

    <div
      v-show="panel === 'evidence'"
      id="report-side-panel-evidence"
      role="tabpanel"
      aria-labelledby="report-side-tab-evidence"
      class="rr-side__panel"
      data-testid="report-side-evidence"
    >
      <section
        v-if="ctx.evidence.value.status === 'omitted'"
        class="rr-side__omitted"
        role="alert"
        data-testid="report-evidence-omitted"
      >
        <p class="rr-side__omitted-title">{{ t('views.run.report.side.omitted.title') }}</p>
        <p class="rr-side__text">{{ t('views.run.report.side.omitted.body') }}</p>
        <ul v-if="ctx.evidence.value.omission.validation_errors.length > 0" class="rr-side__errors">
          <li v-for="err in ctx.evidence.value.omission.validation_errors" :key="err">{{ err }}</li>
        </ul>
      </section>
      <p
        v-else-if="ctx.evidence.value.status === 'failed'"
        class="rr-side__problem"
        role="alert"
        data-testid="report-evidence-failed"
      >
        {{ t('views.run.report.side.evidenceFailed', { reason: ctx.evidence.value.reason }) }}
      </p>
      <p v-else-if="ctx.evidence.value.status === 'loading'" class="rr-side__text" role="status" data-testid="report-evidence-loading">
        {{ t('views.run.report.side.evidenceLoading') }}
      </p>
      <slot name="evidence">
        <p class="rr-side__text" data-testid="report-evidence-placeholder">{{ t('views.run.report.side.evidencePlaceholder') }}</p>
      </slot>
    </div>

    <div
      v-show="panel === 'questions'"
      id="report-side-panel-questions"
      role="tabpanel"
      aria-labelledby="report-side-tab-questions"
      class="rr-side__panel"
      data-testid="report-side-questions"
    >
      <slot name="questions">
        <p class="rr-side__text" data-testid="report-questions-placeholder">{{ t('views.run.report.side.questionsPlaceholder') }}</p>
      </slot>
    </div>
  </aside>
</template>

<style scoped>
.rr-side {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}
.rr-side__tabs {
  display: flex;
  gap: 4px;
}
.rr-side__tab {
  height: 30px;
  padding: 0 12px;
  border: 0;
  border-radius: var(--ag-r-8);
  background: transparent;
  color: var(--fg2);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}
.rr-side__tab:hover {
  background: var(--s2);
  color: var(--fg);
}
.rr-side__tab[aria-selected='true'] {
  background: var(--s3);
  color: var(--fg);
  font-weight: 650;
}
.rr-side__tab:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.rr-side__panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.rr-side__text {
  margin: 0;
  font-size: 13px;
  color: var(--fg2);
}
.rr-side__omitted {
  padding: 10px 12px;
  border: 1px solid var(--warn);
  border-radius: var(--ag-r-12);
  background: var(--warn-soft);
  color: var(--fg);
}
.rr-side__omitted-title {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 650;
}
.rr-side__errors {
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: 12px;
}
.rr-side__problem {
  margin: 0;
  font-size: 13px;
  color: var(--err);
}
</style>
