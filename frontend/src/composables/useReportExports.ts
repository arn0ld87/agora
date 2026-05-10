import type { ComputedRef, Ref } from 'vue'
import { exportReport } from '../api/report'
import { parseReportContract, type EvidenceMap } from '../contracts/reportContract'

interface UseReportExportsOptions {
  reportId: () => string | undefined
  reportMarkdown: ComputedRef<string>
  reportHtml: ComputedRef<string>
  evidenceMap: Ref<EvidenceMap | null>
  addLog: (message: string) => void
  recordSchemaError: (where: string, error: unknown) => void
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 500)
}

export function buildStandaloneHtml(title: string, bodyHtml: string) {
  return `<!doctype html>
<html lang="de"><head><meta charset="utf-8" />
<title>${title}</title>
<style>
  body { font-family: Georgia, 'Iowan Old Style', serif; max-width: 740px; margin: 48px auto; padding: 0 24px; color: #111; line-height: 1.6; font-size: 16px; }
  h1,h2,h3,h4 { font-family: Georgia, serif; line-height: 1.25; margin: 2em 0 0.4em; }
  h1 { font-size: 2em; border-bottom: 1px solid #ccc; padding-bottom: 0.3em; }
  h2 { font-size: 1.5em; }
  h3 { font-size: 1.2em; }
  p { margin: 0.8em 0; }
  ul, ol { margin: 0.8em 0 0.8em 1.4em; }
  li { margin: 0.3em 0; }
  blockquote { border-left: 3px solid #e2681a; margin: 1em 0; padding: 0.2em 1em; color: #555; font-style: italic; }
  code { background: #f3f3f3; padding: 2px 4px; border-radius: 3px; font-size: 0.92em; }
  pre { background: #1a1a1a; color: #eee; padding: 1em; overflow: auto; border-radius: 4px; }
  pre code { background: transparent; color: inherit; padding: 0; }
  table { border-collapse: collapse; margin: 1em 0; }
  th, td { border: 1px solid #ccc; padding: 6px 10px; }
  .conf-badge { display: inline-block; border-radius: 4px; padding: 1px 6px; font-family: system-ui, sans-serif; font-size: 0.82em; font-weight: 700; line-height: 1.5; }
  .conf-low { background: #fff3cd; color: #7a4b00; border: 1px solid #e7b84f; }
  .conf-medium { background: #e7f0ff; color: #174ea6; border: 1px solid #9bbcff; }
  .conf-high { background: #e6f6ed; color: #17633a; border: 1px solid #90d3aa; }
  hr { border: 0; border-top: 1px solid #ccc; margin: 2em 0; }
  @media print { body { margin: 0; padding: 24px; } }
</style>
</head>
<body>
<h1>${title}</h1>
${bodyHtml}
</body></html>`
}

export function useReportExports(options: UseReportExportsOptions) {
  async function downloadMarkdown() {
    const md = options.reportMarkdown.value
    const reportId = options.reportId()
    if (!reportId) return
    let blob: Blob
    try {
      blob = await exportReport(reportId, 'md')
    } catch (e) {
      if (!md) {
        options.addLog('Markdown-Export fehlgeschlagen: ' + ((e as Error)?.message || String(e)))
        return
      }
      blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    }
    triggerDownload(
      blob,
      `agora-report-${reportId}.md`
    )
  }

  function downloadHtml() {
    const reportId = options.reportId()
    const html = buildStandaloneHtml(
      `Agora-Report · ${reportId || ''}`,
      options.reportHtml.value
    )
    triggerDownload(
      new Blob([html], { type: 'text/html;charset=utf-8' }),
      `agora-report-${reportId}.html`
    )
  }

  function printReport() {
    const reportId = options.reportId()
    const html = buildStandaloneHtml(
      `Agora-Report · ${reportId || ''}`,
      options.reportHtml.value
    )
    const w = window.open('', '_blank')
    if (!w) {
      options.addLog('Popup blockiert — bitte Popups erlauben.')
      return
    }
    w.document.open()
    w.document.write(html)
    w.document.close()
    w.addEventListener('load', () => {
      setTimeout(() => w.print(), 200)
    })
  }

  async function copyMarkdown() {
    const md = options.reportMarkdown.value
    if (!md) return
    try {
      await navigator.clipboard.writeText(md)
      options.addLog('Markdown in Zwischenablage kopiert.')
    } catch (e) {
      options.addLog('Kopieren fehlgeschlagen: ' + (e as Error).message)
    }
  }

  function downloadEvidence() {
    const evidenceMap = options.evidenceMap.value
    const reportId = options.reportId()
    if (!evidenceMap || !reportId) return
    triggerDownload(
      new Blob([JSON.stringify(evidenceMap, null, 2)], { type: 'application/json;charset=utf-8' }),
      `agora-report-${reportId}-evidence.json`
    )
  }

  async function downloadCombinedJson() {
    const reportId = options.reportId()
    if (!reportId) return
    try {
      const blob = await exportReport(reportId, 'json')
      const text = await blob.text()
      const json = JSON.parse(text)
      const parsed = parseReportContract(json)
      if (!parsed.ok) {
        options.recordSchemaError('export', { issues: parsed.errors })
        options.addLog('JSON-Export: Schema-Mismatch — siehe rote Box')
        return
      }
      const validatedBlob = new Blob([JSON.stringify(parsed.data, null, 2)], { type: 'application/json;charset=utf-8' })
      triggerDownload(validatedBlob, `agora-report-${reportId}.json`)
    } catch (e) {
      options.addLog('JSON-Export fehlgeschlagen: ' + ((e as Error)?.message || String(e)))
    }
  }

  return {
    copyMarkdown,
    downloadCombinedJson,
    downloadEvidence,
    downloadHtml,
    downloadMarkdown,
    printReport,
  }
}
