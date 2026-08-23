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
    // Issue #1160 A: Geltungsbereich der Confidence. Spiegelt
    // backend/app/contracts/report_v3.py::Claim.confidence_scope.
    // Optional/nullable, weil report-v3.json aus der Zeit davor das Feld
    // nicht traegt — nicht erfasst ist nicht dasselbe wie
    // "simulation_consensus" und darf deshalb keinen Default bekommen.
    confidence_scope: z
      .enum(["simulation_consensus", "evidence", "empirical"])
      .optional()
      .nullable(),
    // Issue #1012: Stufe, unter der der statement-Wortlaut entstand. Nur
    // gesetzt, wenn der Claim nachtraeglich abgestuft wurde — dann deckt
    // seine Formulierung mehr Sicherheit ab, als das Label ausweist.
    // null/undefined heisst "nicht abgestuft", nicht "unbekannt".
    text_confidence: z
      .enum(["speculative", "low", "medium", "high", "verified"])
      .optional()
      .nullable(),
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

// === Threshold (Issue #1160 E, erweitert um #1343) ===
// Operative Zahlen tragen ihre Herkunft mit. `origin` ist eine eigene
// Dimension neben EvidenceSourceKind — die Quellengattung beschreibt, woher
// ein Beleg kommt, `origin` beschreibt, wie eine Zahl zustande kam.
//
// Issue #1343: `kind` trennt operative Mengen ("quantity") von Datumsangaben
// ("date"). Aus „15. Oktober 2026" entstand sonst der sinnlose Eintrag
// value=15.0 / unit="October". Das Feld ist optional/nullable, weil
// Bestandsartefakte es nicht tragen — „nicht erfasst" ist nicht dasselbe wie
// eine erfasste quantity (Muster: Claim.confidence_scope).
// Issue #1343: Ein Monatsname ist keine Maßeinheit. Steht er als unit in einem
// numerischen Threshold, war der Ursprung eine Datumsangabe, deren Tag und Monat
// die Extraktion auseinandergerissen hat — ohne Jahr nicht rekonstruierbar.
const THRESHOLD_MONTH_NAMES = new Set([
  "januar",
  "january",
  "februar",
  "february",
  "märz",
  "maerz",
  "march",
  "april",
  "mai",
  "may",
  "juni",
  "june",
  "juli",
  "july",
  "august",
  "september",
  "oktober",
  "october",
  "november",
  "dezember",
  "december",
]);

export const ThresholdSchema = z
  .object({
    id: z.string().min(1),
    label: z.string().min(1),
    kind: z.enum(["quantity", "date"]).nullable().default(null),
    value: z.union([z.number(), z.string()]),
    unit: z.string().min(1).nullable().optional(),
    purpose: z.enum(["alert", "target", "limit", "baseline"]),
    origin: z.enum([
      "document_requirement",
      "empirical_data",
      "external_standard",
      "operator_policy",
      "model_proposal",
      "simulation_proposal",
    ]),
    evidence_status: z.enum(["verified", "derived", "heuristic"]).default("heuristic"),
    evidence_refs: z.array(EvidenceIdSchema).default([]),
  })
  .strict()
  .superRefine((value, ctx) => {
    // Spiegelt Threshold.verified_needs_an_evidence_ref: eine Zahl als belegt
    // auszuweisen, ohne einen Beleg zu nennen, ist genau die Behauptung, die
    // #1160 E adressiert.
    if (value.evidence_status === "verified" && value.evidence_refs.length === 0) {
      ctx.addIssue({
        code: "custom",
        path: ["evidence_refs"],
        message: "evidence_status='verified' verlangt mindestens eine evidence_ref.",
      });
    }

    // Spiegelt Threshold.kind_matches_value_shape (#1343): ein Datum trägt
    // keine Einheit und nur einen ISO-Wert; eine Menge ist eine echte Zahl
    // mit Einheit — ein Monatsname ist keine Einheit.
    if (value.kind === "date") {
      if (typeof value.value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value.value)) {
        ctx.addIssue({
          code: "custom",
          path: ["value"],
          message:
            "kind='date' verlangt einen ISO-Datumswert ('YYYY-MM-DD').",
        });
      }
      if (value.unit != null) {
        ctx.addIssue({
          code: "custom",
          path: ["unit"],
          message: "kind='date' trägt keine Einheit — ein Datum ist keine Menge.",
        });
      }
    } else {
      if (typeof value.value === "string") {
        ctx.addIssue({
          code: "custom",
          path: ["value"],
          message:
            "Nur kind='date' darf einen Textwert tragen; operative Schwellwerte sind Zahlen.",
        });
      }
      if (!value.unit || !value.unit.trim()) {
        ctx.addIssue({
          code: "custom",
          path: ["unit"],
          message: "Eine operative Zahl braucht eine Einheit (unit).",
        });
      } else if (THRESHOLD_MONTH_NAMES.has(value.unit.trim().toLowerCase())) {
        ctx.addIssue({
          code: "custom",
          path: ["unit"],
          message: `'${value.unit}' ist ein Monatsname, keine Einheit.`,
        });
      }
    }
  });
export type Threshold = z.infer<typeof ThresholdSchema>;

// === DataGap ===
export const DataGapSchema = z
  .object({
    id: z.string().min(1),
    beschreibung: z.string().min(1),
    severity: z.enum(["low", "medium", "high"]),
    suggested_fixes: z.array(z.string()).default([]),
    // Issue #1319: exportierte Hypothesen-ID (H<n>_<i> / HA<n>_<i>), wenn die
    // Luecke aus demselben Claim stammt wie eine Hypothese des Artefakts.
    related_hypothesis_id: z.string().nullable().default(null),
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

/**
 * Issue #1192: Stand der Simulation zum Startzeitpunkt der Reportgenerierung.
 *
 * Ein Report darf auf einem Zwischenstand beruhen — er muss nur ausweisen,
 * dass er es tut. Spiegelt `SimulationSnapshotModel` aus
 * `backend/app/contracts/report_contract.py`.
 */
export const SimulationSnapshotSchema = z
  .object({
    rounds_completed: z.number().int().nonnegative(),
    total_rounds: z.number().int().nonnegative().default(0),
    simulation_running: z.boolean().default(false),
    captured_at: z.string().nullable().default(null),
  })
  .strict();
export type SimulationSnapshot = z.infer<typeof SimulationSnapshotSchema>;

/**
 * Issue #1304 (S3): Anteil der validierten Aussagen, den die Simulation traegt.
 * Anteile sind null, solange es keine validierte Aussage gibt — eine 0 wuerde
 * "kein Beitrag" behaupten, wo nichts gemessen wurde.
 */
export const SimulationContributionSchema = z
  .object({
    validated_claims: z.number().int().nonnegative().default(0),
    claims_with_simulation_evidence: z.number().int().nonnegative().default(0),
    claims_with_action_evidence: z.number().int().nonnegative().default(0),
    claims_requiring_action_evidence: z.number().int().nonnegative().default(0),
    simulation_share: z.number().min(0).max(1).nullable().default(null),
    action_share: z.number().min(0).max(1).nullable().default(null),
    action_necessary_share: z.number().min(0).max(1).nullable().default(null),
  })
  .strict();
export type SimulationContribution = z.infer<typeof SimulationContributionSchema>;

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
    // Issue #1160 E: operative Zahlen mit ausgewiesener Herkunft.
    thresholds: z.array(ThresholdSchema).default([]),
    // Slice 5 (Issue #497): Red-Team-Befunde — max 10, Backward-compat default [].
    red_team_findings: z.array(z.string()).max(10).default([]),
    model_attribution: z.array(ModelAttributionSchema).default([]),
    // Issue #1192: Simulationsstand zum Startzeitpunkt des Reports. Nullable
    // mit Default — Bestandsreports ohne den Slot bleiben gueltig.
    simulation_snapshot: SimulationSnapshotSchema.nullable().default(null),
    simulation_contribution: SimulationContributionSchema.nullable().default(null),
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
      { path: "thresholds", entries: value.thresholds },
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
