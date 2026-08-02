import { z } from 'zod';

/**
 * Pipeline-Degradierung — Zod-Spiegel zu
 * `backend/app/contracts/pipeline_degradation_contract.py` (Issue #1029).
 *
 * An mehreren Stellen der Pipeline lieferte ein Teilausfall ein Ergebnis,
 * das wie ein gutes aussah: das Embedding fiel aus und alle Vektoren
 * blieben leer, der Graph entstand ohne eine einzige Kante, die
 * Persona-Generierung fiel auf ein regelbasiertes Platzhalterprofil
 * zurück. Der Schritt meldete Erfolg, und der Qualitätsverlust schlug
 * erst viel später als scheinbar unzusammenhängendes Symptom durch.
 *
 * Abgrenzung zu `EvidenceDegradationSchema` (Issue #1006, reportContract):
 * das protokolliert die Abstufung eines einzelnen Claims im fertigen
 * Report. Hier geht es um den Ausfall eines Pipeline-Schritts, lange bevor
 * ein Report existiert.
 */

export const DEGRADATION_KINDS = [
  'embedding_unavailable',
  'graph_below_threshold',
  'persona_rule_based_fallback',
] as const;

export const DegradationKindSchema = z.enum(DEGRADATION_KINDS);
export type DegradationKind = z.infer<typeof DegradationKindSchema>;

/**
 * `blocking` heißt: Der Schritt darf den Zustand „bereit" nicht erreichen,
 * auch wenn technisch kein Fehler aufgetreten ist.
 */
export const DegradationSeveritySchema = z.enum(['warning', 'blocking']);
export type DegradationSeverity = z.infer<typeof DegradationSeveritySchema>;

export const PipelineDegradationSchema = z.object({
  kind: DegradationKindSchema,
  severity: DegradationSeveritySchema,
  detail: z.string().min(1),
  // Spiegelt `datetime` im Backend-Vertrag. `offset: true` lässt sowohl
  // `Z` als auch `+HH:MM` zu — Pydantic serialisiert je nach tzinfo beides.
  occurred_at: z.iso.datetime({ offset: true }),
  /** Gleichartige Ereignisse werden backend-seitig zusammengefasst. */
  occurrences: z.number().int().min(1).default(1),
  context: z.record(z.string(), z.union([z.string(), z.number()])).default({}),
}).strict();
export type PipelineDegradation = z.infer<typeof PipelineDegradationSchema>;

export const PipelineDegradationReportSchema = z.object({
  schema_version: z.number().int().min(1).default(1),
  events: z.array(PipelineDegradationSchema).default([]),
}).strict();
export type PipelineDegradationReport = z.infer<typeof PipelineDegradationReportSchema>;

export const EMPTY_DEGRADATION_REPORT: PipelineDegradationReport = {
  schema_version: 1,
  events: [],
};

/**
 * Liest den Degradierungs-Report aus einem Task-Ergebnis.
 *
 * Bewusst tolerant: Ein Task-Ergebnis von vor #1029 trägt das Feld nicht,
 * und ein unlesbares Feld darf den Build-Abschluss nicht verhindern —
 * sonst würde ein Hinweismechanismus zum Ausfallgrund. In beiden Fällen
 * ist das Ergebnis ein leerer Report.
 */
export function parseDegradationReport(
  result: Record<string, unknown> | null | undefined,
): PipelineDegradationReport {
  if (!result || typeof result !== 'object') return EMPTY_DEGRADATION_REPORT;
  const parsed = PipelineDegradationReportSchema.safeParse(result.degradations);
  return parsed.success ? parsed.data : EMPTY_DEGRADATION_REPORT;
}

/** True, sobald mindestens ein Ereignis den Schritt blockiert. */
export function hasBlockingDegradation(report: PipelineDegradationReport): boolean {
  return report.events.some((event) => event.severity === 'blocking');
}
