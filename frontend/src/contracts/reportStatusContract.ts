import { z } from 'zod';

/**
 * Report-Status — Zod-Spiegel zu
 * `backend/app/contracts/report_status_contract.py` (Issue #1174, Muster
 * aus #1458).
 *
 * `ReportStatusService.get_status` loest den Status ueber eine Kette von
 * Strategien auf (siehe Modul-Docstring dort). Dieser Contract deckt vier
 * dieser fuenf Stufen ab — Run-Registry, persistierter Report, Simulation,
 * Acknowledge-Polling —, die alle dieselbe Envelope-Form teilen. Die fuenfte
 * Stufe (ein lebender Task, `Task.to_dict()`) bleibt aussen vor; sie hat eine
 * ganz andere Feldmenge und keinen eigenen Backend-Contract. Deshalb ist
 * `parseReportStatusResponse` bewusst NICHT in `useReportGeneration.ts`s
 * Polling verdrahtet — es wuerde jede Task-Branch-Antwort als
 * Validierungsfehler ablehnen.
 */

/**
 * Vereinigung der Status-Werte aus allen vier abgedeckten Stufen: die
 * Run-Registry-Stufe reicht ihren Rohwert durch (inkl. "incomplete",
 * Issue #1277-2), die anderen drei setzen "completed"/"failed"/"generating"
 * fest.
 */
export const ReportStatusValueSchema = z.enum([
  'pending',
  'processing',
  'paused',
  'completed',
  'failed',
  'stopped',
  'incomplete',
  'generating',
]);
export type ReportStatusValue = z.infer<typeof ReportStatusValueSchema>;

/**
 * Stabile i18n-Schluessel — siehe `i18n/statusMessage.ts` +
 * `locales/{de,en}.json`. Optional: "incomplete"/"stopped" aus der
 * Run-Registry-Stufe tragen (noch) keinen Schluessel (Randzustaende
 * ausserhalb von #1174).
 */
export const ReportMessageKeySchema = z.enum([
  'report.generated',
  'report.failed',
  'report.awaiting_task',
  'report.generating',
]);
export type ReportMessageKey = z.infer<typeof ReportMessageKeySchema>;

export const ReportStatusResponseSchema = z
  .object({
    simulation_id: z.string().optional(),
    report_id: z.string().optional(),
    status: ReportStatusValueSchema,
    progress: z.number().int().min(0).max(100),
    message: z.string(),
    message_key: ReportMessageKeySchema.optional(),
    error: z.string().optional(),
    already_completed: z.boolean().optional(),
    // Nur in der Run-Registry-Stufe (`_status_from_run_registry`).
    run_id: z.string().optional(),
    missing_sections: z.array(z.string()).optional(),
    // Form gespiegelt aus `ReportExportService.map_outline_for_contract`
    // ({title, summary, sections}); bewusst kein strikterer Contract — siehe
    // Begruendung im Backend-Pendant.
    outline: z.record(z.string(), z.unknown()).optional(),
    sections: z.record(z.string(), z.record(z.string(), z.unknown())).optional(),
    current_section_index: z.number().int().optional(),
  })
  .strict();

export type ReportStatusResponse = z.infer<typeof ReportStatusResponseSchema>;

/**
 * Tolerant beim Lesen, analog `parsePersonaTarget`: ein unerwartetes Feld
 * darf das Polling nicht kippen — der Aufrufer faellt bei einem Miss auf
 * die lose getypte `ReportStatusData`/`ReportGenerationStatusData` zurueck.
 */
export function parseReportStatusResponse(value: unknown): ReportStatusResponse | null {
  const result = ReportStatusResponseSchema.safeParse(value);
  return result.success ? result.data : null;
}
