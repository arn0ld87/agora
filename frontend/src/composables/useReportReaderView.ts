/**
 * useReportReaderView — Outline und Abschnitts-HTML fuer den ReportReader
 * gemeinsam bestimmen (PR 6, Redesign-Serie 2026-09).
 *
 * Warum zusammen und nicht getrennt: ReportReader rendert Abschnitt i aus
 * `sectionHtml[i]`. Eine Outline mit N Abschnitten neben einem einzigen
 * HTML-Block ergibt N-1 leere Abschnitte. Genau das entstand, solange Outline
 * und HTML unabhaengig voneinander ihren Fallback waehlten: ein aus der
 * Persistenz geladener Bericht (`_status_from_persisted_report`) liefert den
 * Bericht als Ganzes, aber keine `generated_sections` — die Outline kam dann
 * aus der Evidence-Map mit allen Abschnitten, das HTML bestand aus einem Block,
 * und jeder Abschnitt ausser dem ersten blieb leer.
 *
 * Diese Funktion macht die Kopplung strukturell: es gibt nur einen Rueckgabe-
 * wert, der beide Haelften traegt, und sie koennen nicht mehr auseinander-
 * laufen.
 *
 * Der Preis ist bewusst gewaehlt: faellt die Outline auf einen Sammelabschnitt
 * zurueck, erreicht der Belegrand nur noch die Aussagen von Abschnitt 1 — er
 * folgt der aktiven Abschnittsnummer. Das ist der kleinere Schaden. Ein
 * vollstaendig lesbarer Bericht ist der Zweck dieser Ansicht; die uebrigen
 * Belege bleiben ueber die Anhangszaehler und den Evidence-JSON-Export
 * erreichbar, waehrend leere Abschnitte den Bericht als kaputt erscheinen
 * liessen. Sobald `generated_sections` vorliegen — also bei jedem frisch
 * erzeugten Bericht — greift dieser Zweig ohnehin nicht.
 *
 * Bewusst zustandslos und ohne Vue-Abhaengigkeit — die Auswahl ist ohne Mount
 * testbar (analog useSimulationLiveMetrics.ts).
 */
import type { ReportOutline, ReportSection } from '@/contracts/reportContract'

export interface ReportReaderViewInput {
  /** Outline aus dem Report-/Status-Payload, `null` bei Legacy-Berichten. */
  outline: ReportOutline | null | undefined
  /** Gerendertes Markdown je Abschnittsnummer, aus `generated_sections`. */
  sectionHtml: Record<string, string>
  /** Der komplette Bericht als ein HTML-Block. */
  reportHtml: string
  /** Abschnitte der Evidenzkarte — zweitbeste Quelle fuer Abschnittstitel. */
  evidenceSections: readonly ReportSection[]
  /** Titel, wenn die Outline keinen mitbringt (i18n `step4.title`). */
  fallbackTitle: string
  /** Label des Sammelabschnitts (i18n `step4.reader.outlineFullReport`). */
  fullReportLabel: string
}

export interface ReportReaderView {
  outline: ReportOutline
  sectionHtml: Record<string, string>
}

export function buildReportReaderView(input: ReportReaderViewInput): ReportReaderView {
  const hasSectionHtml = Object.keys(input.sectionHtml).length > 0

  if (hasSectionHtml) {
    if (input.outline) {
      return { outline: input.outline, sectionHtml: input.sectionHtml }
    }
    if (input.evidenceSections.length) {
      return {
        outline: {
          title: input.fallbackTitle,
          summary: '',
          sections: input.evidenceSections.map((section) => ({
            title: section.section_title,
            description: section.section_summary || section.section_title,
          })),
        },
        sectionHtml: input.sectionHtml,
      }
    }
  }

  // Kein Abschnitts-HTML: der Bericht liegt nur als ein Block vor, also traegt
  // genau ein Abschnitt ihn vollstaendig. Titel und Zusammenfassung der echten
  // Outline bleiben erhalten, wenn es sie gibt — verloren geht nur die
  // Abschnittsnavigation, und die zeigte hier ohnehin ins Leere.
  return {
    outline: {
      title: input.outline?.title || input.fallbackTitle,
      summary: input.outline?.summary || '',
      sections: [{ title: input.fullReportLabel, description: '' }],
    },
    sectionHtml: { 1: input.reportHtml },
  }
}
