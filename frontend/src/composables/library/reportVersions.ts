import { z } from 'zod'
import { ReportSchema } from '../../contracts/reportContract'
import { reportStatusState, type LibraryState } from './runState'

/**
 * Fassungen eines Laufs aus `GET /api/report/list?simulation_id=…` (#1797).
 *
 * Die Antwort wird gegen den Zod-Spiegel geprueft: eine Fassung, die den
 * Vertrag verletzt, wird gezaehlt und gemeldet, nicht still mitgerendert.
 * Modell und Anbieter stammen aus dem Berichts-Job (#1804) und sind optional:
 * ohne Angabe nennt die Zeile wie bisher nur Fassung, Datum und Zustand.
 */

export interface ReportVersion {
  reportId: string
  /** 1 = aelteste Fassung. */
  number: number
  createdAt: string
  state: LibraryState
  /** Gelaufenes Modell dieser Fassung; `null`, wenn der Bericht keines belegt. */
  model: string | null
  /** Anbieter-ID des gelaufenen Modells; `null`, wenn nicht belegt. */
  providerId: string | null
}

export type ReportVersionsResult =
  | { ok: true; versions: ReportVersion[]; invalid: number }
  | { ok: false }

const EnvelopeSchema = z.object({
  success: z.boolean(),
  data: z.array(z.unknown()).nullish(),
})

/** Neueste Fassung zuerst; die Nummer zaehlt vom aeltesten Bericht aufwaerts. */
export function parseReportVersions(envelope: unknown): ReportVersionsResult {
  const outer = EnvelopeSchema.safeParse(envelope)
  if (!outer.success || !outer.data.success || !outer.data.data) return { ok: false }
  const reports: Array<{
    reportId: string
    createdAt: string
    status: string
    model: string | null
    providerId: string | null
  }> = []
  let invalid = 0
  for (const item of outer.data.data) {
    const parsed = ReportSchema.safeParse(item)
    if (!parsed.success) {
      invalid += 1
      continue
    }
    const r = parsed.data
    reports.push({
      reportId: r.report_id,
      createdAt: r.completed_at || r.created_at || '',
      status: r.status,
      model: r.llm_model || null,
      providerId: r.llm_provider_id || null,
    })
  }
  reports.sort((a, b) => a.createdAt.localeCompare(b.createdAt))
  const versions = reports
    .map((r, i) => ({
      reportId: r.reportId,
      number: i + 1,
      createdAt: r.createdAt,
      state: reportStatusState(r.status),
      model: r.model,
      providerId: r.providerId,
    }))
    .reverse()
  return { ok: true, versions, invalid }
}
