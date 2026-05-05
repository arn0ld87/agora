/**
 * GraphDiff-Contract v1 — Zod-Spiegel.
 *
 * Hand-gepflegt, 1:1 zu schemas/graph-diff.schema.json.
 * Änderungen am Pydantic-Modell (backend/app/contracts/graph_diff.py)
 * → Schema-Dump → diese Datei synchronisieren.
 */
import { z } from "zod";

// === EdgeData ===
export const EdgeDataSchema = z
  .object({
    uuid: z.string(),
    source_id: z.string(),
    target_id: z.string(),
    relation_type: z.string(),
    weight: z.number().nullable().optional(),
    reinforced_count: z.number().int().nullable().optional(),
    properties: z
      .record(z.string(), z.union([z.string(), z.number(), z.boolean()]))
      .default(() => ({})),
  })
  .strict();
export type EdgeData = z.infer<typeof EdgeDataSchema>;

// === NodePropertyShift ===
export const NodePropertyShiftSchema = z
  .object({
    node_id: z.string(),
    node_label: z.string(),
    property_name: z.string(),
    before: z
      .union([z.string(), z.number(), z.boolean(), z.null()])
      .nullable()
      .optional(),
    after: z
      .union([z.string(), z.number(), z.boolean(), z.null()])
      .nullable()
      .optional(),
  })
  .strict();
export type NodePropertyShift = z.infer<typeof NodePropertyShiftSchema>;

// === ClusterShift ===
export const ClusterShiftSchema = z
  .object({
    agent_id: z.number().int(),
    cluster_a_id: z.number().int(),
    cluster_a_label: z.string(),
    cluster_b_id: z.number().int(),
    cluster_b_label: z.string(),
    cluster_a_size: z.number().int().nonnegative(),
    cluster_b_size: z.number().int().nonnegative(),
  })
  .strict();
export type ClusterShift = z.infer<typeof ClusterShiftSchema>;

// === BridgeAgentShift ===
export const BridgeAgentShiftSchema = z
  .object({
    agent_id: z.number().int(),
    action: z.enum(["joined_top_k", "left_top_k"]),
    centrality_before: z.number().min(0).max(1).nullable().optional(),
    centrality_after: z.number().min(0).max(1).nullable().optional(),
    tier: z.string().nullable().optional(),
  })
  .strict();
export type BridgeAgentShift = z.infer<typeof BridgeAgentShiftSchema>;

// === ClusterSummary ===
export const ClusterSummarySchema = z
  .object({
    cluster_id: z.number().int(),
    size: z.number().int().nonnegative(),
    label: z.string(),
    member_count: z.number().int().nonnegative(),
  })
  .strict();
export type ClusterSummary = z.infer<typeof ClusterSummarySchema>;

// === GraphSnapshot ===
export const GraphSnapshotSchema = z
  .object({
    graph_id: z.string(),
    round_num: z.number().int().nullable().optional(),
    snapshot_id: z.string().nullable().optional(),
    created_at: z.string(),
    node_count: z.number().int().nonnegative(),
    edge_count: z.number().int().nonnegative(),
    edges: z.array(EdgeDataSchema).default(() => []),
    density: z.number().min(0).max(1),
    cluster_count: z.number().int().nonnegative(),
    dominant_clusters: z.array(ClusterSummarySchema).default(() => []),
    bridge_agents: z.array(z.number().int()).default(() => []),
  })
  .strict();
export type GraphSnapshot = z.infer<typeof GraphSnapshotSchema>;

// === EdgeReinforcement ===
export const EdgeReinforcementSchema = z
  .object({
    edge: EdgeDataSchema,
    weight_before: z.number(),
    weight_after: z.number(),
    reinforced_count_before: z.number().int().nonnegative(),
    reinforced_count_after: z.number().int().nonnegative(),
  })
  .strict()
  .refine((val) => val.weight_after >= val.weight_before, {
    message:
      "EdgeReinforcement: weight_after muss >= weight_before sein. Kanten mit sinkendem Gewicht bitte in EdgeWeakening eintragen.",
    path: ["weight_after"],
  });
export type EdgeReinforcement = z.infer<typeof EdgeReinforcementSchema>;

// === EdgeWeakening ===
export const EdgeWeakeningSchema = z
  .object({
    edge: EdgeDataSchema,
    weight_before: z.number(),
    weight_after: z.number(),
    reinforced_count_before: z.number().int().nonnegative(),
    reinforced_count_after: z.number().int().nonnegative(),
  })
  .strict()
  .refine((val) => val.weight_after < val.weight_before, {
    message:
      "EdgeWeakening: weight_after muss < weight_before sein. Kanten mit steigendem oder gleichem Gewicht bitte in EdgeReinforcement eintragen.",
    path: ["weight_after"],
  });
export type EdgeWeakening = z.infer<typeof EdgeWeakeningSchema>;

// === GraphDiffMetrics ===
export const GraphDiffMetricsSchema = z
  .object({
    total_edges_added: z.number().int().nonnegative(),
    total_edges_removed: z.number().int().nonnegative(),
    total_edges_reinforced: z.number().int().nonnegative(),
    total_edges_weakened: z.number().int().nonnegative(),
    avg_reinforcement_delta: z.number(),
    avg_weakening_delta: z.number(),
    density_delta: z.number(),
    node_properties_changed: z.number().int().nonnegative(),
    agents_changed_clusters: z.number().int().nonnegative(),
    clusters_new: z.number().int().nonnegative(),
    clusters_removed: z.number().int().nonnegative(),
    bridge_agents_joined: z.number().int().nonnegative(),
    bridge_agents_left: z.number().int().nonnegative(),
  })
  .strict();
export type GraphDiffMetrics = z.infer<typeof GraphDiffMetricsSchema>;

// === GraphDiff (Top-Level) ===
export const GraphDiffSchema = z
  .object({
    graph_id: z.string(),
    snapshot_a_id: z.string(),
    snapshot_b_id: z.string(),
    created_at: z.string(),
    comparison_type: z.enum(["round-to-round", "branch-diff"]),
    snapshot_a: GraphSnapshotSchema,
    snapshot_b: GraphSnapshotSchema,
    edges_added: z.array(EdgeDataSchema).default(() => []),
    edges_removed: z.array(EdgeDataSchema).default(() => []),
    edges_reinforced: z.array(EdgeReinforcementSchema).default(() => []),
    edges_weakened: z.array(EdgeWeakeningSchema).default(() => []),
    node_properties_changed: z.array(NodePropertyShiftSchema).default(() => []),
    cluster_shifts: z.array(ClusterShiftSchema).default(() => []),
    clusters_new: z.array(ClusterSummarySchema).default(() => []),
    clusters_removed: z.array(ClusterSummarySchema).default(() => []),
    bridge_agent_shifts: z.array(BridgeAgentShiftSchema).default(() => []),
    metrics: GraphDiffMetricsSchema,
  })
  .strict();
export type GraphDiff = z.infer<typeof GraphDiffSchema>;
