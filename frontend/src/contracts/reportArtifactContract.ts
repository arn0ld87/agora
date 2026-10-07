/**
 * Antwort-Envelopes der Berichts-Artefakte — Zod-Spiegel (Issue #1804, Etappe 5).
 *
 * Hand-gepflegt, 1:1 zu:
 *   schemas/evidence-density-response.schema.json
 *   schemas/stance-analysis-response.schema.json
 *
 * Änderungen am Pydantic-Modell
 * (backend/app/contracts/report_artifact_contract.py)
 * → Schema-Dump → diese Datei synchronisieren.
 *
 * Wire-Form von `GET /api/report/<id>/evidence-density` und
 * `GET /api/report/<id>/stance-analysis`: genau zwei Varianten.
 *   - `{ success: true, data }`: die gespeicherte Datei ist vertragsgültig.
 *   - `{ success: true, artifact_omitted }`: die Datei liegt vor, verletzt aber
 *     den Vertrag. Das ist sichtbar zu machen, nicht als „keine Daten" zu lesen.
 * Eine fehlende Datei (Altbericht) ist HTTP 404, also ein Fehler-Envelope.
 */
import { z } from "zod";
import { EvidenceDensitySchema } from "./evidenceDensityContract";
import { StanceAnalysisSchema } from "./stanceAnalysisContract";

export const ReportArtifactKindSchema = z.enum(["evidence_density", "stance_analysis"]);
export type ReportArtifactKind = z.infer<typeof ReportArtifactKindSchema>;

/**
 * `reason` ist der stabile Schlüssel, aus dem die Oberfläche per vue-i18n
 * übersetzt. `detail` ist kein UI-Text und wird nicht gerendert.
 */
export const ReportArtifactOmissionSchema = z
  .object({
    artifact: ReportArtifactKindSchema,
    reason: z.literal("contract_violation"),
    detail: z.string().min(1),
    validation_errors: z.array(z.string()).max(5).default([]),
  })
  .strict();
export type ReportArtifactOmission = z.infer<typeof ReportArtifactOmissionSchema>;

export const EvidenceDensityResponseSuccessSchema = z
  .object({ success: z.literal(true), data: EvidenceDensitySchema })
  .strict();

export const EvidenceDensityResponseOmittedSchema = z
  .object({ success: z.literal(true), artifact_omitted: ReportArtifactOmissionSchema })
  .strict();

export const EvidenceDensityResponseSchema = z.union([
  EvidenceDensityResponseSuccessSchema,
  EvidenceDensityResponseOmittedSchema,
]);
export type EvidenceDensityResponse = z.infer<typeof EvidenceDensityResponseSchema>;

export const StanceAnalysisResponseSuccessSchema = z
  .object({ success: z.literal(true), data: StanceAnalysisSchema })
  .strict();

export const StanceAnalysisResponseOmittedSchema = z
  .object({ success: z.literal(true), artifact_omitted: ReportArtifactOmissionSchema })
  .strict();

export const StanceAnalysisResponseSchema = z.union([
  StanceAnalysisResponseSuccessSchema,
  StanceAnalysisResponseOmittedSchema,
]);
export type StanceAnalysisResponse = z.infer<typeof StanceAnalysisResponseSchema>;
