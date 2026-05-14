/**
 * ReportV3-Contract — Zod-Spiegel.
 *
 * Hand-gepflegt, 1:1 zu schemas/report-v3.schema.json und
 * backend/app/contracts/report_v3.py.
 *
 * Wording-Glossar v1: VERBOTEN sind "prediction", "rehearsal",
 * "god's eye view", "future prediction". Erlaubt: Simulation,
 * Szenarienanalyse, Reaktionsmuster, Einschätzung.
 *
 * Änderungen am Pydantic-Modell → Schema-Dump → diese Datei synchronisieren.
 * M11.8c Vorbereitung für M11.8d (Strict-Schema-Forced-Output).
 */
import { z } from "zod";

// === Persona ===
export const PersonaV3Schema = z
  .object({
    id: z.string().min(1),
    voice_register: z.enum([
      "formal-de",
      "neutral-de",
      "technical-de",
      "skeptisch-de",
    ]),
    alter_range: z.string().min(1),
    beruf: z.string().min(1),
    region: z.string().min(1),
    bildungsgrad: z.string().nullable().optional(),
    haushaltseinkommen: z.string().nullable().optional(),
    needs: z.array(z.string()).default([]),
    values: z.array(z.string()).default([]),
    evidence_refs: z.array(z.string()).default([]),
  })
  .strict();
export type PersonaV3 = z.infer<typeof PersonaV3Schema>;

// === Segment ===
export const SegmentSchema = z
  .object({
    id: z.string().min(1),
    name: z.string().min(1),
    beschreibung: z.string().min(1),
    persona_ids: z.array(z.string()).default([]),
    kontaktwahrscheinlichkeit_prozent: z
      .number()
      .min(0)
      .max(100)
      .nullable()
      .optional(),
  })
  .strict();
export type Segment = z.infer<typeof SegmentSchema>;

// === Claim ===
export const ClaimSchema = z
  .object({
    id: z.string().min(1),
    statement: z.string().min(8),
    evidence_refs: z.array(z.string()).min(1),
    confidence: z.enum(["low", "medium", "high"]),
    persona_ids: z.array(z.string()).default([]),
    aggregation_basis: z.enum([
      "seed",
      "persona",
      "aggregat",
      "datenluecke",
    ]),
  })
  .strict();
export type Claim = z.infer<typeof ClaimSchema>;

// === Multiplier ===
export const MultiplierSchema = z
  .object({
    id: z.string().min(1),
    name: z.string().min(1),
    kategorie: z.enum([
      "awareness",
      "consideration",
      "conversion",
      "retention",
    ]),
    reichweite_score: z.number().int().min(1).max(10),
    evidence_refs: z.array(z.string()).default([]),
  })
  .strict();
export type Multiplier = z.infer<typeof MultiplierSchema>;

// === FrictionPoint ===
export const FrictionPointSchema = z
  .object({
    id: z.string().min(1),
    beschreibung: z.string().min(1),
    severity: z.enum(["low", "medium", "high"]),
    affected_persona_ids: z.array(z.string()).default([]),
    evidence_refs: z.array(z.string()).default([]),
  })
  .strict();
export type FrictionPoint = z.infer<typeof FrictionPointSchema>;

// === TrustSignal ===
export const TrustSignalSchema = z
  .object({
    id: z.string().min(1),
    beschreibung: z.string().min(1),
    signal_type: z.enum([
      "social_proof",
      "authority",
      "consistency",
      "reciprocity",
      "scarcity",
      "liking",
    ]),
    evidence_refs: z.array(z.string()).default([]),
  })
  .strict();
export type TrustSignal = z.infer<typeof TrustSignalSchema>;

// === ChangeRecommendation ===
export const ChangeRecommendationSchema = z
  .object({
    id: z.string().min(1),
    titel: z.string().min(1),
    beschreibung: z.string().min(1),
    priority: z.enum(["low", "medium", "high"]),
    aufwand: z.enum(["S", "M", "L"]),
    evidence_refs: z.array(z.string()).default([]),
  })
  .strict();
export type ChangeRecommendation = z.infer<typeof ChangeRecommendationSchema>;

// === ProjectImpact ===
export const ProjectImpactSchema = z
  .object({
    id: z.string().min(1),
    beschreibung: z.string().min(1),
    affected_segments: z.array(z.string()).default([]),
    confidence: z.enum(["low", "medium", "high"]),
    evidence_refs: z.array(z.string()).default([]),
  })
  .strict();
export type ProjectImpact = z.infer<typeof ProjectImpactSchema>;

// === PositioningVariant ===
export const PositioningVariantSchema = z
  .object({
    id: z.string().min(1),
    titel: z.string().min(1),
    claim_text: z.string().min(1),
    ziel_persona_ids: z.array(z.string()).default([]),
    evidence_refs: z.array(z.string()).default([]),
  })
  .strict();
export type PositioningVariant = z.infer<typeof PositioningVariantSchema>;

// === ContentIdea ===
export const ContentIdeaSchema = z
  .object({
    id: z.string().min(1),
    titel: z.string().min(1),
    format: z.enum([
      "blog",
      "video",
      "podcast",
      "social",
      "whitepaper",
      "webinar",
      "other",
    ]),
    persona_ids: z.array(z.string()).default([]),
    evidence_refs: z.array(z.string()).default([]),
  })
  .strict();
export type ContentIdea = z.infer<typeof ContentIdeaSchema>;

// === DataGap ===
export const DataGapSchema = z
  .object({
    id: z.string().min(1),
    beschreibung: z.string().min(1),
    severity: z.enum(["low", "medium", "high"]),
    suggested_fixes: z.array(z.string()).default([]),
  })
  .strict();
export type DataGap = z.infer<typeof DataGapSchema>;

// === Hypothesis ===
export const HypothesisSchema = z
  .object({
    id: z.string().min(1),
    hypothesis_text: z.string().min(1),
    rationale: z.string().default(""),
    suggested_evidence: z.array(z.string()).default([]),
    origin_section_index: z.number().int().nullable().optional(),
    confidence_score: z.number().min(0).max(1).default(0),
  })
  .strict();
export type Hypothesis = z.infer<typeof HypothesisSchema>;

// === ReportMode ===
export const ReportModeSchema = z.enum(["strict", "balanced", "explorative"]);
export type ReportMode = z.infer<typeof ReportModeSchema>;
export const DEFAULT_REPORT_MODE: ReportMode = "balanced";

// === ReportV3 Container ===
export const ReportV3Schema = z
  .object({
    schema_version: z.literal(3),
    report_id: z.string().min(1),
    generated_at: z.string().datetime(),
    report_mode: ReportModeSchema.default("balanced"),
    personas: z.array(PersonaV3Schema).default([]),
    segments: z.array(SegmentSchema).default([]),
    claims: z.array(ClaimSchema).default([]),
    multipliers: z.array(MultiplierSchema).default([]),
    friction_points: z.array(FrictionPointSchema).default([]),
    trust_signals: z.array(TrustSignalSchema).default([]),
    change_recommendations: z.array(ChangeRecommendationSchema).default([]),
    project_impacts: z.array(ProjectImpactSchema).default([]),
    positioning_variants: z.array(PositioningVariantSchema).default([]),
    content_ideas: z.array(ContentIdeaSchema).default([]),
    data_gaps: z.array(DataGapSchema).default([]),
    hypotheses: z.array(HypothesisSchema).default([]),
  })
  .strict();
export type ReportV3 = z.infer<typeof ReportV3Schema>;

/**
 * Parse-Funktion für ReportV3-Payloads — spiegelt backend-seitige Validierung.
 * Bei Fehler: strukturierte ZodIssue-Liste zurückgeben, NICHT mit `?.` weiterrendern.
 */
export function parseReportV3(
  raw: unknown,
): { ok: true; data: ReportV3 } | { ok: false; errors: z.ZodIssue[] } {
  const result = ReportV3Schema.safeParse(raw);
  return result.success
    ? { ok: true, data: result.data }
    : { ok: false, errors: result.error.issues };
}
