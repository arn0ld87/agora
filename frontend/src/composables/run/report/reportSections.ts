/**
 * Gliederung und Lesetext des Berichts (Etappe 5, #1804), rein und ohne Netzwerk.
 *
 * Der Zustand je Abschnitt kommt nur aus dem, was der Bestand trägt:
 *  - `missing`: der Titel steht in `Report.missing_sections`,
 *  - `failed`: `generation_failed` am Abschnitt (Status-Poll oder Evidence-Map),
 *  - `pending`: Erzeugung läuft, der Abschnitt hat noch keinen Text,
 *  - `ready`: sonst.
 * Fehlende Abschnitte, die zu keinem Gliederungstitel passen, erscheinen als
 * eigene Einträge am Ende, nie verschluckt. Der Lesetext nutzt dieselbe
 * Auswahl (`buildReportReaderView`) und dieselbe sanitisierte Markdown-Funktion
 * (`renderMarkdown`, DOMPurify) wie `Step4Report`.
 */
import type { ReportOutline, ReportSection } from '@/contracts/reportContract'
import { buildReportReaderView } from '@/composables/useReportReaderView'
import { renderMarkdown } from '@/utils/markdown'

export type SectionState = 'ready' | 'missing' | 'failed' | 'pending'

export interface OutlineEntry {
  /** 1-basiert; Einträge ohne Gliederungstitel (nur in `missing_sections`) zählen dahinter weiter. */
  index: number
  title: string
  state: SectionState
}

export interface OutlineInput {
  outline: ReportOutline | null | undefined
  evidenceSections: readonly ReportSection[]
  missingSections: readonly string[]
  /** `sections` des Status-Polls: Schlüssel `"1"`, `"2"`, … mit `content` und `generation_failed`. */
  generatedSections: Record<string, unknown>
  /** Berichtsstatus; `null`, solange nichts geladen ist. */
  reportStatus: string | null
}

function norm(value: string): string {
  return value.trim().toLocaleLowerCase('de')
}

function generatedAt(sections: Record<string, unknown>, index: number): { content: string; failed: boolean } | null {
  const raw = sections[String(index)]
  if (raw === undefined || raw === null) return null
  if (typeof raw === 'string') return { content: raw, failed: false }
  if (typeof raw === 'object') {
    const obj = raw as { content?: unknown; generation_failed?: unknown }
    return {
      content: typeof obj.content === 'string' ? obj.content : '',
      failed: obj.generation_failed === true,
    }
  }
  return null
}

export function deriveOutline(input: OutlineInput): OutlineEntry[] {
  const titles: string[] = input.outline
    ? input.outline.sections.map((s) => s.title)
    : input.evidenceSections.map((s) => s.section_title)
  const missing = input.missingSections.map(norm)
  const terminal = input.reportStatus === 'completed' || input.reportStatus === 'incomplete'
  const matchedMissing = new Set<number>()

  const entries: OutlineEntry[] = titles.map((title, i) => {
    const index = i + 1
    const missingAt = missing.indexOf(norm(title))
    if (missingAt >= 0) matchedMissing.add(missingAt)
    const generated = generatedAt(input.generatedSections, index)
    const evidenceFailed = input.evidenceSections.some((s) => s.section_index === index && s.generation_failed)
    let state: SectionState
    if (missingAt >= 0) state = 'missing'
    else if (generated?.failed || evidenceFailed) state = 'failed'
    else if (generated && generated.content) state = 'ready'
    else state = terminal ? 'ready' : 'pending'
    return { index, title, state }
  })

  input.missingSections.forEach((title, i) => {
    if (matchedMissing.has(i)) return
    entries.push({ index: entries.length + 1, title, state: 'missing' })
  })
  return entries
}

export interface ReadingSection extends OutlineEntry {
  /** Bereits sanitisiertes HTML (`renderMarkdown`); leer, wenn es noch keinen Text gibt. */
  html: string
}

export interface ReadingView {
  title: string
  summary: string
  /** `sections`: Text je Abschnitt (frisch erzeugt). `whole`: gespeicherter Bericht als ein Block. */
  mode: 'sections' | 'whole'
  sections: ReadingSection[]
  wholeHtml: string
}

export interface ReadingInput extends OutlineInput {
  markdownContent: string
  fallbackTitle: string
}

export function deriveReading(input: ReadingInput): ReadingView {
  const outline = deriveOutline(input)
  const sectionHtml: Record<string, string> = {}
  for (const entry of outline) {
    const generated = generatedAt(input.generatedSections, entry.index)
    if (generated && generated.content) sectionHtml[String(entry.index)] = renderMarkdown(generated.content)
  }
  const view = buildReportReaderView({
    outline: input.outline,
    sectionHtml,
    reportHtml: renderMarkdown(input.markdownContent),
    evidenceSections: input.evidenceSections,
    fallbackTitle: input.fallbackTitle,
    fullReportLabel: '',
  })
  // Ohne Gliederung gäbe es keinen Platz für den Text je Abschnitt: dann als ein Block.
  const perSection = Object.keys(sectionHtml).length > 0 && outline.length > 0
  return {
    title: view.outline.title,
    summary: view.outline.summary,
    mode: perSection ? 'sections' : 'whole',
    sections: outline.map((entry) => ({ ...entry, html: sectionHtml[String(entry.index)] ?? '' })),
    wholeHtml: perSection ? '' : renderMarkdown(input.markdownContent),
  }
}
