/**
 * BranchComparison-Contract v1 — Zod-Spiegel.
 *
 * Hand-gepflegt, 1:1 zu schemas/branch-comparison.schema.json.
 * Änderungen am Pydantic-Modell (backend/app/contracts/branch_comparison.py)
 * → Schema-Dump → diese Datei synchronisieren.
 * Reuse: ClusterSummary aus graphDiffContract (Single Source of Truth — KEIN Duplikat).
 */
import { z } from "zod";
import {
  ClusterSummarySchema,
  type ClusterSummary,
} from "./graphDiffContract";

// Re-Export für Konsumenten, die nur dieses Modul importieren
export { ClusterSummarySchema, type ClusterSummary };

// Typisierter Literal-Typ für Confidence-Distribution-Keys (Pendant zu Pydantic _ConfidenceKey)
const _ConfidenceKeySchema = z.enum(["speculative", "low", "medium", "high", "verified"]);
export type ConfidenceKey = z.infer<typeof _ConfidenceKeySchema>;

// === SegmentReach ===
export const SegmentReachSchema = z
  .object({
    segment_name: z.string(),
    active_count: z.number().int().nonnegative(),
    total_count: z.number().int().nonnegative(),
    ratio: z.number().min(0.0).max(1.0),
  })
  .strict()
  .refine((val) => val.active_count <= val.total_count, {
    message:
      "SegmentReach: active_count darf nicht größer als total_count sein.",
    path: ["active_count"],
  })
  .refine(
    (val) => {
      if (val.total_count === 0) {
        return val.ratio === 0.0;
      }
      return Math.abs(val.ratio - val.active_count / val.total_count) < 1e-6;
    },
    {
      message:
        "SegmentReach: ratio stimmt nicht mit active_count/total_count überein (Toleranz 1e-6) oder ist nicht 0.0 bei total_count==0.",
      path: ["ratio"],
    }
  );
export type SegmentReach = z.infer<typeof SegmentReachSchema>;

// === ClusterChange ===
export const ClusterChangeSchema = z
  .object({
    cluster_id: z.number().int(),
    size_a: z.number().int().nonnegative(),
    size_b: z.number().int().nonnegative(),
    label_a: z.string(),
    label_b: z.string(),
  })
  .strict();
export type ClusterChange = z.infer<typeof ClusterChangeSchema>;

// === BranchMetrics ===
export const BranchMetricsSchema = z
  .object({
    // --- Netzwerk ---
    echo_chamber_index: z.number().min(0.0).max(1.0),
    cluster_count: z.number().int().nonnegative(),
    dominant_clusters: z.array(ClusterSummarySchema).default(() => []),
    bridge_agent_ids: z.array(z.number().int()).default(() => []),
    total_agents: z.number().int().nonnegative(),
    total_interactions: z.number().int().nonnegative(),
    interaction_density: z.number().min(0.0),
    // --- Report / Evidence ---
    confidence_distribution: z
      .object({
        speculative: z.number().int().nonnegative().optional().default(0),
        low: z.number().int().nonnegative(),
        medium: z.number().int().nonnegative(),
        high: z.number().int().nonnegative(),
        verified: z.number().int().nonnegative(),
      })
      .strict(),
    avg_evidence_per_claim: z.number().min(0.0),
    claims_without_evidence_ratio: z.number().min(0.0).max(1.0),
    contradiction_ratio: z.number().min(0.0).max(1.0),
    // --- Personas ---
    persona_reach: z.record(z.string(), SegmentReachSchema).default(() => ({})),
  })
  .strict();
export type BranchMetrics = z.infer<typeof BranchMetricsSchema>;

// === ComparisonDeltas ===
export const ComparisonDeltasSchema = z
  .object({
    // --- Netzwerk-Deltas ---
    echo_chamber_delta: z.number(),
    cluster_delta: z.number().int(),
    bridge_agents_delta: z.number().int(),
    // --- Evidence-Qualität-Deltas ---
    confidence_distribution_delta: z
      .object({
        speculative: z.number().int().optional().default(0),
        low: z.number().int(),
        medium: z.number().int(),
        high: z.number().int(),
        verified: z.number().int(),
      })
      .strict(),
    avg_evidence_delta: z.number(),
    contradiction_ratio_delta: z.number(),
    // --- Engagement-Delta ---
    interaction_density_delta: z.number(),
    // --- Semantische Cluster-Highlights ---
    clusters_only_in_a: z.array(ClusterSummarySchema).default(() => []),
    clusters_only_in_b: z.array(ClusterSummarySchema).default(() => []),
    clusters_changed: z.array(ClusterChangeSchema).default(() => []),
  })
  .strict();
export type ComparisonDeltas = z.infer<typeof ComparisonDeltasSchema>;

// === BranchComparison (Top-Level) ===
export const BranchComparisonSchema = z
  .object({
    simulation_id: z.string(),
    branch_a_id: z.string(),
    branch_b_id: z.string(),
    // Zeitstempel: offset-aware ISO-8601 oder plain ISO (wie graphDiffContract)
    created_at: z.string(),
    branch_a_completed_at: z.string(),
    branch_b_completed_at: z.string(),
    // Metriken pro Branch
    metrics_a: BranchMetricsSchema,
    metrics_b: BranchMetricsSchema,
    // Differenzen (B - A)
    deltas: ComparisonDeltasSchema,
  })
  .strict()
  .refine((val) => val.branch_a_id !== val.branch_b_id, {
    message:
      "BranchComparison: branch_a_id und branch_b_id müssen verschieden sein.",
    path: ["branch_b_id"],
  });
export type BranchComparison = z.infer<typeof BranchComparisonSchema>;
