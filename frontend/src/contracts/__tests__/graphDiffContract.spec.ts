/**
 * Zod-Spiegel-Tests für GraphDiffContract v1.
 *
 * Backend-Quelle: backend/app/contracts/graph_diff.py
 * Schema: schemas/graph-diff.schema.json
 */
import { describe, it, expect } from "vitest";
import {
  GraphDiffSchema,
  EdgeDataSchema,
  EdgeReinforcementSchema,
  EdgeWeakeningSchema,
} from "../graphDiffContract";

// --- Fixture-Helpers ---

function makeEdge(uuid: string) {
  return {
    uuid,
    source_id: "node-1",
    target_id: "node-2",
    relation_type: "RELATES_TO",
    weight: 1.0,
    reinforced_count: null,
    properties: {},
  };
}

function makeSnapshot(graphId: string) {
  return {
    graph_id: graphId,
    round_num: 1,
    snapshot_id: `snap-${graphId}`,
    created_at: "2026-05-05T10:00:00Z",
    node_count: 5,
    edge_count: 3,
    edges: [],
    density: 0.3,
    cluster_count: 2,
    dominant_clusters: [],
    bridge_agents: [],
  };
}

function makeMetrics(overrides = {}) {
  return {
    total_edges_added: 0,
    total_edges_removed: 0,
    total_edges_reinforced: 0,
    total_edges_weakened: 0,
    avg_reinforcement_delta: 0.0,
    avg_weakening_delta: 0.0,
    density_delta: 0.0,
    node_properties_changed: 0,
    agents_changed_clusters: 0,
    clusters_new: 0,
    clusters_removed: 0,
    bridge_agents_joined: 0,
    bridge_agents_left: 0,
    ...overrides,
  };
}

function makeMinimalDiff() {
  return {
    graph_id: "graph-abc",
    snapshot_a_id: "snap-a",
    snapshot_b_id: "snap-b",
    created_at: "2026-05-05T10:00:00Z",
    comparison_type: "round-to-round" as const,
    snapshot_a: makeSnapshot("graph-abc"),
    snapshot_b: makeSnapshot("graph-abc"),
    edges_added: [],
    edges_removed: [],
    edges_reinforced: [],
    edges_weakened: [],
    node_properties_changed: [],
    cluster_shifts: [],
    clusters_new: [],
    clusters_removed: [],
    bridge_agent_shifts: [],
    metrics: makeMetrics(),
  };
}

// --- Tests ---

describe("GraphDiffSchema", () => {
  describe("minimales Fixture (alle Required-Felder, leere Listen)", () => {
    it("akzeptiert valides minimales Diff", () => {
      const result = GraphDiffSchema.safeParse(makeMinimalDiff());
      expect(result.success).toBe(true);
    });

    it("gibt typisiertes GraphDiff-Objekt zurück", () => {
      const diff = GraphDiffSchema.parse(makeMinimalDiff());
      expect(diff.graph_id).toBe("graph-abc");
      expect(diff.comparison_type).toBe("round-to-round");
      expect(diff.edges_added).toEqual([]);
    });
  });

  describe("reiches Fixture (2 added Edges, 1 reinforced, 1 weakened, 1 ClusterShift, 1 BridgeAgentShift)", () => {
    it("akzeptiert valides reiches Diff", () => {
      const richDiff = {
        ...makeMinimalDiff(),
        edges_added: [makeEdge("edge-add-1"), makeEdge("edge-add-2")],
        edges_reinforced: [
          {
            edge: makeEdge("edge-reinf-1"),
            weight_before: 1.0,
            weight_after: 2.0,
            reinforced_count_before: 0,
            reinforced_count_after: 1,
          },
        ],
        edges_weakened: [
          {
            edge: makeEdge("edge-weak-1"),
            weight_before: 3.0,
            weight_after: 1.5,
            reinforced_count_before: 2,
            reinforced_count_after: 1,
          },
        ],
        cluster_shifts: [
          {
            agent_id: 42,
            cluster_a_id: 1,
            cluster_a_label: "Gruppe A",
            cluster_b_id: 2,
            cluster_b_label: "Gruppe B",
            cluster_a_size: 10,
            cluster_b_size: 8,
          },
        ],
        bridge_agent_shifts: [
          {
            agent_id: 7,
            action: "joined_top_k" as const,
            centrality_before: 0.1,
            centrality_after: 0.6,
            tier: "top-5",
          },
        ],
        metrics: makeMetrics({
          total_edges_added: 2,
          total_edges_reinforced: 1,
          total_edges_weakened: 1,
        }),
      };

      const result = GraphDiffSchema.safeParse(richDiff);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.edges_added).toHaveLength(2);
        expect(result.data.edges_reinforced).toHaveLength(1);
        expect(result.data.edges_weakened).toHaveLength(1);
        expect(result.data.cluster_shifts).toHaveLength(1);
        expect(result.data.bridge_agent_shifts[0].action).toBe("joined_top_k");
      }
    });
  });

  describe("comparison_type Validierung", () => {
    it("akzeptiert 'round-to-round'", () => {
      const result = GraphDiffSchema.safeParse({
        ...makeMinimalDiff(),
        comparison_type: "round-to-round",
      });
      expect(result.success).toBe(true);
    });

    it("akzeptiert 'branch-diff'", () => {
      const result = GraphDiffSchema.safeParse({
        ...makeMinimalDiff(),
        comparison_type: "branch-diff",
      });
      expect(result.success).toBe(true);
    });

    it("lehnt unbekannten comparison_type ab → ZodError", () => {
      const result = GraphDiffSchema.safeParse({
        ...makeMinimalDiff(),
        comparison_type: "wrong",
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues.length).toBeGreaterThan(0);
      }
    });
  });

  describe("EdgeReinforcement: weight_after >= weight_before", () => {
    it("akzeptiert gleiches Gewicht (equal)", () => {
      const result = EdgeReinforcementSchema.safeParse({
        edge: makeEdge("e1"),
        weight_before: 2.0,
        weight_after: 2.0,
        reinforced_count_before: 0,
        reinforced_count_after: 0,
      });
      expect(result.success).toBe(true);
    });

    it("lehnt weight_after < weight_before ab → ZodError", () => {
      const result = EdgeReinforcementSchema.safeParse({
        edge: makeEdge("e1"),
        weight_before: 3.0,
        weight_after: 1.0,
        reinforced_count_before: 0,
        reinforced_count_after: 0,
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        const msg = result.error.issues.map((i) => i.message).join(" ");
        expect(msg).toMatch(/weight_after/i);
      }
    });
  });

  describe("EdgeWeakening: weight_after < weight_before", () => {
    it("lehnt weight_after >= weight_before ab → ZodError", () => {
      const result = EdgeWeakeningSchema.safeParse({
        edge: makeEdge("e2"),
        weight_before: 1.0,
        weight_after: 2.0,
        reinforced_count_before: 0,
        reinforced_count_after: 0,
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        const msg = result.error.issues.map((i) => i.message).join(" ");
        expect(msg).toMatch(/weight_after/i);
      }
    });

    it("lehnt gleiches Gewicht ab (not strictly less)", () => {
      const result = EdgeWeakeningSchema.safeParse({
        edge: makeEdge("e2"),
        weight_before: 2.0,
        weight_after: 2.0,
        reinforced_count_before: 0,
        reinforced_count_after: 0,
      });
      expect(result.success).toBe(false);
    });
  });

  describe(".strict() — kein extra-Feld erlaubt", () => {
    it("lehnt EdgeData mit extra-Feld ab → ZodError", () => {
      const result = EdgeDataSchema.safeParse({
        uuid: "e1",
        source_id: "n1",
        target_id: "n2",
        relation_type: "RELATES_TO",
        extra: "x",
      });
      expect(result.success).toBe(false);
    });

    it("lehnt GraphDiff mit extra-Feld ab", () => {
      const result = GraphDiffSchema.safeParse({
        ...makeMinimalDiff(),
        unknown_field: true,
      });
      expect(result.success).toBe(false);
    });
  });
});
