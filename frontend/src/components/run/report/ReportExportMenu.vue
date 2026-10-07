<script setup lang="ts">
/**
 * Export-Menü und Druckansicht des Berichts (Etappe 5, #1804, Bauplan 4.6),
 * im Slot `actions` des Kopfs. Die Formate sind die des Bestands (Markdown,
 * Markdown kopieren, HTML, JSON, Evidence-JSON, CSV je Tabelle, ZIP-Bündel);
 * dazu „Drucken“. Das Menü ist das Menü des Designsystems (`DropdownMenu`,
 * reka-ui: Pfeiltasten, Pos1/Ende, Esc, Fokus zurück).
 *
 * Gesperrt (mit sichtbarer Erklärung, `aria-disabled`, bleibt fokussierbar):
 * keine Fassung gewählt, Bericht lädt oder wird noch erzeugt. Ein
 * `incomplete`-Bericht bleibt exportierbar; das Menü sagt „unvollständig“ dazu.
 *
 * Fortschritt: `role="status"`; Fehler und „ohne Belege ausgeliefert“:
 * `role="alert"`.
 *
 * Druck: `window.print()`. Das unscoped `@media print` unten blendet alles
 * außer `.run-report` aus (Seitenleiste, Reiter, Gliederung, Seitenspalte,
 * Knöpfe), nimmt Lesebreite und Spalten weg, druckt das Hinweisband
 * „Was fehlt“ mit und schreibt Linkadressen hinter Links. Die Kopfzeile des
 * Drucks (Titel, Fassung, Zustand) ist `.rep-export__print`.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import DropdownMenu from '@/components/v4/forms/DropdownMenu.vue'
import DropdownMenuItem from '@/components/v4/forms/DropdownMenuItem.vue'
import { reportStateKind } from '@/composables/run/runStageState'
import { useRunReportContext } from '@/composables/run/report/useRunReport'
import { useReportExport, type ExportAction } from '@/composables/run/report/useReportExport'
import { renderMarkdown } from '@/utils/markdown'

const { t } = useI18n()
const ctx = useRunReportContext()

const reportData = computed(() => (ctx.report.value.status === 'ok' ? ctx.report.value.report : null))
const version = computed(() =>
  ctx.versions.value.status === 'ok'
    ? (ctx.versions.value.items.find((v) => v.reportId === ctx.selectedReportId.value) ?? null)
    : null,
)
const status = computed(() => reportData.value?.status ?? version.value?.status ?? null)
const running = computed(() => !!status.value && reportStateKind(status.value) === 'running')
const incomplete = computed(() => status.value === 'incomplete')

/** Grund der Sperre, sonst `null`. */
const blocked = computed<'noVersion' | 'loading' | 'running' | null>(() => {
  if (!ctx.selectedReportId.value) return 'noVersion'
  if (running.value) return 'running'
  if (!reportData.value) return 'loading'
  return null
})

const markdown = computed(() => reportData.value?.markdown_content ?? '')
const evidenceMap = computed(() => (ctx.evidence.value.status === 'ok' ? ctx.evidence.value.map : null))

const exporter = useReportExport({
  reportId: () => (blocked.value ? null : ctx.selectedReportId.value),
  markdown: () => markdown.value,
  html: () => renderMarkdown(markdown.value),
  evidenceMap: () => evidenceMap.value,
  omittedReason: () => t('views.run.report.export.omittedReason'),
})

const FORMATS: ReadonlyArray<{ action: ExportAction; needsEvidence?: boolean }> = [
  { action: 'md' },
  { action: 'copy' },
  { action: 'html' },
  { action: 'json' },
  { action: 'evidence', needsEvidence: true },
  { action: 'csv-personas' },
  { action: 'csv-segments' },
  { action: 'csv-claims' },
  { action: 'zip' },
]

const busy = computed(() => exporter.state.value.status === 'running')
const actionLabel = (a: ExportAction): string => t(`views.run.report.export.action.${a}`)

const failure = computed(() => {
  const s = exporter.state.value
  return s.status === 'failed' || s.status === 'warning' ? s : null
})
const statusText = computed(() => {
  const s = exporter.state.value
  if (s.status === 'running') return t('views.run.report.export.running', { action: actionLabel(s.action) })
  if (s.status === 'done') return t('views.run.report.export.done', { action: actionLabel(s.action) })
  return ''
})

const printTitle = computed(() => t('views.run.report.print.title', { title: reportTitle.value }))
const reportTitle = computed(() => ctx.reading.value.title || t('views.run.report.reading.untitled'))
const printVersion = computed(() =>
  version.value ? t('views.run.report.print.version', { n: version.value.number }) : '',
)
const printState = computed(() =>
  status.value ? t(`views.run.state.${reportStateKind(status.value)}`) : '',
)

function onPrint(): void {
  void exporter.run('print')
}
</script>

<template>
  <div class="rep-export" data-testid="report-export">
    <DropdownMenu v-if="!blocked" align="end">
      <template #trigger>
        <button
          type="button"
          class="rep-export__trigger"
          :aria-busy="busy"
          data-testid="report-export-trigger"
        >
          {{ t('views.run.report.export.trigger') }}
        </button>
      </template>
      <p v-if="incomplete" class="rep-export__incomplete" data-testid="report-export-incomplete">
        {{ t('views.run.report.export.incomplete') }}
      </p>
      <DropdownMenuItem
        v-for="f in FORMATS"
        :key="f.action"
        :disabled="busy || (f.needsEvidence && !evidenceMap)"
        :data-testid="`report-export-${f.action}`"
        @select="exporter.run(f.action)"
      >
        {{ actionLabel(f.action) }}
        <span v-if="f.needsEvidence && !evidenceMap" class="rep-export__hint">
          {{ t('views.run.report.export.noEvidence') }}
        </span>
      </DropdownMenuItem>
      <DropdownMenuItem :disabled="busy" data-testid="report-export-print" @select="onPrint">
        {{ actionLabel('print') }}
      </DropdownMenuItem>
    </DropdownMenu>
    <template v-else>
      <button
        type="button"
        class="rep-export__trigger rep-export__trigger--blocked"
        aria-disabled="true"
        aria-describedby="report-export-blocked"
        data-testid="report-export-trigger"
        @click.prevent
      >
        {{ t('views.run.report.export.trigger') }}
      </button>
      <span id="report-export-blocked" class="rep-export__note" data-testid="report-export-blocked">
        {{ t(`views.run.report.export.blocked.${blocked}`) }}
      </span>
    </template>

    <p class="rep-export__status" role="status" aria-live="polite" data-testid="report-export-status">{{ statusText }}</p>
    <p v-if="failure" class="rep-export__problem" role="alert" data-testid="report-export-problem">
      {{
        t(
          failure.status === 'failed' ? 'views.run.report.export.failed' : 'views.run.report.export.warning',
          { action: actionLabel(failure.action), reason: failure.reason },
        )
      }}
    </p>

    <div class="rep-export__print" data-testid="report-print-head" aria-hidden="true">
      <p class="rep-export__print-title">{{ printTitle }}</p>
      <p class="rep-export__print-meta">{{ [printVersion, printState].filter(Boolean).join(' · ') }}</p>
    </div>
  </div>
</template>

<style scoped>
.rep-export {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
}
.rep-export__trigger {
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s2);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
.rep-export__trigger:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.rep-export__trigger--blocked {
  color: var(--fg3);
  cursor: not-allowed;
}
.rep-export__note,
.rep-export__status {
  margin: 0;
  font-size: 12px;
  color: var(--fg2);
}
.rep-export__problem {
  flex-basis: 100%;
  margin: 0;
  font-size: 13px;
  color: var(--err);
}
.rep-export__status:empty {
  display: none;
}
.rep-export__incomplete {
  margin: 0;
  padding: 6px 10px;
  max-width: 260px;
  border-radius: var(--ag-r-8);
  background: var(--warn-soft);
  color: var(--fg);
  font-size: 12px;
  font-weight: 600;
}
.rep-export__hint {
  font-size: 11px;
  color: var(--fg3);
}
.rep-export__print {
  display: none;
}
</style>

<style>
/*
 * Druckansicht des Berichts. Unscoped, weil sie die App-Hülle (Seitenleiste,
 * Reiter) treffen muss, deren Klassen diese Komponente nicht kennt: alles
 * unsichtbar, nur `.run-report` sichtbar und an den Seitenrand gelegt.
 */
@media print {
  body * {
    visibility: hidden !important;
  }
  .run-report,
  .run-report * {
    visibility: visible !important;
  }
  html,
  body {
    height: auto !important;
    overflow: visible !important;
    background: #fff !important;
  }
  .run-report {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    color: #000;
  }
  /* Nur Kopfzeile des Drucks, Hinweisband und Lesetext. */
  .run-report .run-report__col--outline,
  .run-report .run-report__col--side,
  .run-report .rr-head__field,
  .run-report .rr-head__problem,
  .run-report .rep-export > :not(.rep-export__print),
  .run-report .rr-head__actions > :not(.rep-export),
  .run-report .rr-read button,
  .run-report .rr-read__log,
  .run-report .rr-read__progress {
    display: none !important;
  }
  .run-report .rep-export__print {
    display: block !important;
    margin-bottom: 12px;
  }
  .run-report .rep-export__print-title {
    margin: 0 0 4px;
    font-size: 20px;
    font-weight: 700;
  }
  .run-report .rep-export__print-meta {
    margin: 0;
    font-size: 12px;
  }
  .run-report .run-report__grid {
    display: block !important;
  }
  .run-report .rr-read__text {
    max-width: none !important;
  }
  .run-report .rr-banner {
    break-inside: avoid;
    border: 1px solid #000;
    background: #fff;
  }
  .run-report .rr-read__prose a[href]::after {
    content: ' (' attr(href) ')';
    font-size: 0.85em;
    word-break: break-all;
  }
}
</style>
