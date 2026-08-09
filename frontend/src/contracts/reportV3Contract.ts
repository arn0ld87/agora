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
import {
  EvidenceIdSchema,
  EvidenceIndexSchema,
} from "./reportContract";
export {
  EvidenceIdSchema,
  EvidenceIndexSchema,
  EvidenceRecordSchema,
} from "./reportContract";
export type {
  EvidenceId,
  EvidenceIndex,
  EvidenceRecord,
} from "./reportContract";

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
    evidence_refs: z.array(EvidenceIdSchema).default([]),
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
    evidence_refs: z.array(EvidenceIdSchema).min(1),
    confidence: z.enum(["speculative", "low", "medium", "high", "verified"]),
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
    evidence_refs: z.array(EvidenceIdSchema).default([]),
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
    evidence_refs: z.array(EvidenceIdSchema).default([]),
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
    evidence_refs: z.array(EvidenceIdSchema).default([]),
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
    evidence_refs: z.array(EvidenceIdSchema).default([]),
  })
  .strict();
export type ChangeRecommendation = z.infer<typeof ChangeRecommendationSchema>;

// === ProjectImpact ===
export const ProjectImpactSchema = z
  .object({
    id: z.string().min(1),
    beschreibung: z.string().min(1),
    affected_segments: z.array(z.string()).default([]),
    confidence: z.enum(["speculative", "low", "medium", "high", "verified"]),
    evidence_refs: z.array(EvidenceIdSchema).default([]),
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
    evidence_refs: z.array(EvidenceIdSchema).default([]),
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
    evidence_refs: z.array(EvidenceIdSchema).default([]),
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

// === ModelAttribution (Slice 8 — 2026-05-16) ===
// Spiegelt backend/app/contracts/report_v3.py::ModelAttribution.
// Pro Pipeline-Stage ein Eintrag mit Provider/Modell und optionalen
// Token-/Latency-Metriken. Backward-compat: default [].
// Slice 5 (Issue #497): "red_team" ergänzt.
export const ModelAttributionStageSchema = z.enum([
  "ontology",
  "graph_extraction",
  "simulation",
  "report_outline",
  "report_section",
  "report_synthesis",
  "red_team",
  "evidence_extraction",
  "interview",
  "other",
]);
export type ModelAttributionStage = z.infer<typeof ModelAttributionStageSchema>;

export const ModelAttributionSchema = z
  .object({
    stage: ModelAttributionStageSchema,
    provider: z.string().min(1),
    model_id: z.string().min(1),
    prompt_tokens: z.number().int().nonnegative().nullable().default(null),
    completion_tokens: z.number().int().nonnegative().nullable().default(null),
    latency_ms: z.number().nonnegative().nullable().default(null),
    started_at: z.string().datetime().nullable().default(null),
    note: z.string().max(200).nullable().default(null),
  })
  .strict();
export type ModelAttribution = z.infer<typeof ModelAttributionSchema>;

// === ReportV3 Container ===
export const ReportV3Schema = z
  .object({
    schema_version: z.literal(4),
    report_id: z.string().min(1),
    generated_at: z.string().datetime(),
    evidence_index: EvidenceIndexSchema.default({}),
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
    // Slice 5 (Issue #497): Red-Team-Befunde — max 10, Backward-compat default [].
    red_team_findings: z.array(z.string()).max(10).default([]),
    model_attribution: z.array(ModelAttributionSchema).default([]),
  })
  .strict()
  .superRefine((value, ctx) => {
    const knownIds = new Set(Object.keys(value.evidence_index));
    const refCollections: Array<{
      path: string;
      entries: Array<{ evidence_refs: string[] }>;
    }> = [
      { path: "personas", entries: value.personas },
      { path: "claims", entries: value.claims },
      { path: "multipliers", entries: value.multipliers },
      { path: "friction_points", entries: value.friction_points },
      { path: "trust_signals", entries: value.trust_signals },
      { path: "change_recommendations", entries: value.change_recommendations },
      { path: "project_impacts", entries: value.project_impacts },
      { path: "positioning_variants", entries: value.positioning_variants },
      { path: "content_ideas", entries: value.content_ideas },
    ];

    for (const collection of refCollections) {
      collection.entries.forEach((entry, entryIndex) => {
        entry.evidence_refs.forEach((evidenceId, refIndex) => {
          if (!knownIds.has(evidenceId)) {
            ctx.addIssue({
              code: "custom",
              path: [collection.path, entryIndex, "evidence_refs", refIndex],
              message: `Unbekannte evidence_id '${evidenceId}'.`,
            });
          }
        });
      });
    }
  });
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
