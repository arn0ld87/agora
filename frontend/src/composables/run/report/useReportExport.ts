/**
 * Export des Berichts im Bericht-Reiter (Etappe 5, #1804, Bauplan 4.6).
 *
 * Bietet dieselben Formate und Dateinamen wie der Bestand (`useReportExports`,
 * `api/report.ts`), meldet aber Fortschritt und Fehler als Zustand statt in ein
 * Protokoll, das hier niemand liest:
 *
 *   md        `exportReport(id, 'md')`, bei Transportfehler der geladene Text
 *   copy      Markdown in die Zwischenablage
 *   html      eigenständiges HTML aus dem gesäuberten Lesetext
 *   json      `exportReport(id, 'json')`, gegen `parseReportContract` geprüft
 *   evidence  Evidence-Map als JSON (nur wenn sie geladen ist)
 *   csv-*     `fetchReportCsv` für personas | segments | claims
 *   zip       `fetchReportBundle`
 *   print     `window.print()` (Druck-Stylesheet in `ReportExportMenu.vue`)
 *
 * `state`: idle | running { action } | done { action } | failed { action, reason }
 * | warning { action, reason }. `warning` = Datei ausgeliefert, aber ohne
 * Evidence-Map (`evidence_omitted`); das ist nie ein stiller Erfolg.
 */
import { ref, type Ref } from 'vue'
import { exportReport, fetchReportBundle, fetchReportCsv } from '@/api/report'
import { parseReportContract, type EvidenceMap } from '@/contracts/reportContract'
import { buildStandaloneHtml, triggerDownload } from '@/composables/useReportExports'

export type ExportAction =
  | 'md'
  | 'copy'
  | 'html'
  | 'json'
  | 'evidence'
  | 'csv-personas'
  | 'csv-segments'
  | 'csv-claims'
  | 'zip'
  | 'print'

export type ExportState =
  | { status: 'idle' }
  | { status: 'running'; action: ExportAction }
  | { status: 'done'; action: ExportAction }
  | { status: 'failed'; action: ExportAction; reason: string }
  | { status: 'warning'; action: ExportAction; reason: string }

export interface UseReportExportOptions {
  reportId: () => string | null
  markdown: () => string
  html: () => string
  evidenceMap: () => EvidenceMap | null
  /** Meldung bei `evidence_omitted` im JSON-Export. */
  omittedReason: () => string
  print?: () => void
}

function reasonOf(e: unknown): string {
  return e instanceof Error && e.message ? e.message : String(e)
}

export function useReportExport(options: UseReportExportOptions): {
  state: Ref<ExportState>
  run: (action: ExportAction) => Promise<void>
} {
  const state = ref<ExportState>({ status: 'idle' })

  async function perform(action: ExportAction, id: string): Promise<ExportState | null> {
    switch (action) {
      case 'md': {
        let blob: Blob
        try {
          blob = await exportReport(id, 'md')
        } catch (e) {
          const md = options.markdown()
          if (!md) throw e
          blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
        }
        triggerDownload(blob, `agora-report-${id}.md`)
        return null
      }
      case 'copy': {
        const md = options.markdown()
        if (!md) throw new Error('empty')
        await navigator.clipboard.writeText(md)
        return null
      }
      case 'html': {
        const html = buildStandaloneHtml(`Agora-Report · ${id}`, options.html())
        triggerDownload(new Blob([html], { type: 'text/html;charset=utf-8' }), `agora-report-${id}.html`)
        return null
      }
      case 'json': {
        const blob = await exportReport(id, 'json')
        const parsed = parseReportContract(JSON.parse(await blob.text()))
        if (!parsed.ok) throw new Error(parsed.errors.map((i) => `${i.path.join('.')}: ${i.message}`).join('; '))
        triggerDownload(
          new Blob([JSON.stringify(parsed.data, null, 2)], { type: 'application/json;charset=utf-8' }),
          `agora-report-${id}.json`,
        )
        // Ohne Evidence-Map ausgeliefert: sichtbar, nie als sauberer Erfolg.
        if (parsed.data.evidence_omitted) {
          return { status: 'warning', action, reason: options.omittedReason() }
        }
        return null
      }
      case 'evidence': {
        const map = options.evidenceMap()
        if (!map) throw new Error('no evidence')
        triggerDownload(
          new Blob([JSON.stringify(map, null, 2)], { type: 'application/json;charset=utf-8' }),
          `agora-report-${id}-evidence.json`,
        )
        return null
      }
      case 'csv-personas':
      case 'csv-segments':
      case 'csv-claims': {
        const table = action.slice(4) as 'personas' | 'segments' | 'claims'
        triggerDownload(await fetchReportCsv(id, table), `agora-report-${id}-${table}.csv`)
        return null
      }
      case 'zip':
        triggerDownload(await fetchReportBundle(id), `agora-report-${id}-bundle.zip`)
        return null
      case 'print':
        ;(options.print ?? (() => window.print()))()
        return null
    }
  }

  async function run(action: ExportAction): Promise<void> {
    const id = options.reportId()
    if (!id || state.value.status === 'running') return
    state.value = { status: 'running', action }
    try {
      state.value = (await perform(action, id)) ?? { status: 'done', action }
    } catch (e) {
      state.value = { status: 'failed', action, reason: reasonOf(e) }
    }
  }

  return { state, run }
}
