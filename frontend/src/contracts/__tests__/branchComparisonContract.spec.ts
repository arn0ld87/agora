/**
 * Zod-Spiegel-Tests für BranchComparisonContract v1.
 *
 * Backend-Quelle: backend/app/contracts/branch_comparison.py
 * Schema: schemas/branch-comparison.schema.json
 */
import { describe, it, expect } from "vitest";
import {
  BranchComparisonSchema,
  BranchMetricsSchema,
  SegmentReachSchema,
} from "../branchComparisonContract";

// --- Fixture-Helpers ---

function makeSegmentReach(
  active: number,
  total: number,
  ratio?: number
): object {
  return {
    segment_name: "TestSegment",
    active_count: active,
    total_count: total,
    ratio: ratio ?? (total > 0 ? active / total : 0.0),
  };
}

function makeClusterSummary(id = 1) {
  return {
    cluster_id: id,
    size: 10,
    label: `Cluster-${id}`,
    member_count: 10,
  };
}

function makeClusterChange() {
  return {
    cluster_id: 42,
    size_a: 5,
    size_b: 8,
    label_a: "Alte Gruppe",
    label_b: "Neue Gruppe",
  };
}

function makeConfidenceDist(nonneg = true): object {
  if (nonneg) {
    return { low: 10, medium: 20, high: 15, verified: 5 };
  }
  return { low: -3, medium: 2, high: -1, verified: 0 };
}

function makeMetrics(overrides: Record<string, unknown> = {}): object {
  return {
    echo_chamber_index: 0.4,
    cluster_count: 3,
    dominant_clusters: [],
    bridge_agent_ids: [],
    total_agents: 100,
    total_interactions: 500,
    interaction_density: 5.0,
    confidence_distribution: makeConfidenceDist(),
    avg_evidence_per_claim: 2.5,
    claims_without_evidence_ratio: 0.1,
    contradiction_ratio: 0.05,
    persona_reach: {},
    ...overrides,
  };
}

function makeDeltas(overrides: Record<string, unknown> = {}): object {
  return {
    echo_chamber_delta: 0.05,
    cluster_delta: 1,
    bridge_agents_delta: -2,
    confidence_distribution_delta: { low: -3, medium: 2, high: 1, verified: 0 },
    avg_evidence_delta: 0.3,
    contradiction_ratio_delta: -0.02,
    interaction_density_delta: 1.5,
    clusters_only_in_a: [],
    clusters_only_in_b: [],
    clusters_changed: [],
    ...overrides,
  };
}

function makeMinimalComparison(): object {
  return {
    simulation_id: "sim-001",
    branch_a_id: "branch-a",
    branch_b_id: "branch-b",
    created_at: "2026-05-05T10:00:00Z",
    branch_a_completed_at: "2026-05-05T08:00:00Z",
    branch_b_completed_at: "2026-05-05T09:00:00Z",
    metrics_a: makeMetrics(),
    metrics_b: makeMetrics(),
    deltas: makeDeltas(),
  };
}

// --- Tests ---

describe("BranchComparisonSchema", () => {
  describe("minimales Fixture (alle Required-Felder, leere Listen)", () => {
    it("akzeptiert valides minimales Comparison-Objekt", () => {
      const result = BranchComparisonSchema.safeParse(makeMinimalComparison());
      expect(result.success).toBe(true);
    });

    it("gibt typisiertes BranchComparison-Objekt zurück", () => {
      const comp = BranchComparisonSchema.parse(makeMinimalComparison());
      expect(comp.simulation_id).toBe("sim-001");
      expect(comp.branch_a_id).toBe("branch-a");
      expect(comp.branch_b_id).toBe("branch-b");
      expect(comp.deltas.cluster_delta).toBe(1);
    });
  });

  describe("reiches Fixture (2 dominant_clusters, 1 ClusterChange, 2 SegmentReach)", () => {
    it("akzeptiert valides reiches Fixture", () => {
      const reach: Record<string, object> = {
        Politik: makeSegmentReach(8, 10),
        Wirtschaft: makeSegmentReach(5, 10),
      };
      const richComp = {
        ...makeMinimalComparison(),
        metrics_a: makeMetrics({
          dominant_clusters: [makeClusterSummary(1), makeClusterSummary(2)],
          persona_reach: reach,
        }),
        metrics_b: makeMetrics({
          dominant_clusters: [makeClusterSummary(3), makeClusterSummary(4)],
          persona_reach: reach,
        }),
        deltas: makeDeltas({
          clusters_only_in_a: [makeClusterSummary(10)],
          clusters_only_in_b: [makeClusterSummary(11)],
          clusters_changed: [makeClusterChange()],
        }),
      };
      const result = BranchComparisonSchema.safeParse(richComp);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.metrics_a.dominant_clusters).toHaveLength(2);
        expect(result.data.deltas.clusters_changed).toHaveLength(1);
        expect(
          Object.keys(result.data.metrics_a.persona_reach)
        ).toHaveLength(2);
      }
    });
  });

  describe("BranchComparison.refine: branch_a_id !== branch_b_id", () => {
    it("lehnt identische Branch-IDs ab → ZodError", () => {
      const invalid = {
        ...makeMinimalComparison(),
        branch_a_id: "same-id",
        branch_b_id: "same-id",
      };
      const result = BranchComparisonSchema.safeParse(invalid);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues.length).toBeGreaterThan(0);
      }
    });
  });

  describe(".strict() — kein extra-Feld erlaubt", () => {
    it("lehnt BranchMetrics mit unbekanntem extra-Feld ab → ZodError", () => {
      const metricWithExtra = { ...makeMetrics(), extra: "x" };
      const result = BranchMetricsSchema.safeParse(metricWithExtra);
      expect(result.success).toBe(false);
    });

    it("lehnt BranchComparison mit unbekanntem extra-Feld ab → ZodError", () => {
      const invalid = { ...makeMinimalComparison(), unknown_field: true };
      const result = BranchComparisonSchema.safeParse(invalid);
      expect(result.success).toBe(false);
    });
  });

  describe("confidence_distribution mit unbekanntem Key", () => {
    it("lehnt extra Key in confidence_distribution ab → ZodError", () => {
      const invalidMetrics = makeMetrics({
        confidence_distribution: { low: 1, medium: 2, high: 3, verified: 0, extra: 5 },
      });
      const invalid = {
        ...makeMinimalComparison(),
        metrics_a: invalidMetrics,
      };
      const result = BranchComparisonSchema.safeParse(invalid);
      expect(result.success).toBe(false);
    });
  });

  describe("SegmentReach-Validierungen", () => {
    it("lehnt active_count > total_count ab → ZodError", () => {
      const result = SegmentReachSchema.safeParse(makeSegmentReach(10, 5, 1.0));
      expect(result.success).toBe(false);
      if (!result.success) {
        const msg = result.error.issues.map((i) => i.message).join(" ");
        expect(msg).toMatch(/active_count/i);
      }
    });

    it("lehnt total_count === 0 mit ratio !== 0 ab → ZodError", () => {
      const result = SegmentReachSchema.safeParse({
        segment_name: "Test",
        active_count: 0,
        total_count: 0,
        ratio: 0.5,
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        const msg = result.error.issues.map((i) => i.message).join(" ");
        expect(msg).toMatch(/ratio/i);
      }
    });

    it("akzeptiert total_count === 0 mit ratio === 0 → OK", () => {
      const result = SegmentReachSchema.safeParse({
        segment_name: "LeerSegment",
        active_count: 0,
        total_count: 0,
        ratio: 0.0,
      });
      expect(result.success).toBe(true);
    });

    it("lehnt ratio ab die nicht active/total entspricht → ZodError", () => {
      // active=3, total=10 → ratio sollte 0.3 sein, nicht 0.99
      const result = SegmentReachSchema.safeParse({
        segment_name: "Test",
        active_count: 3,
        total_count: 10,
        ratio: 0.99,
      });
      expect(result.success).toBe(false);
    });

    it("akzeptiert korrektes ratio (3/10 = 0.3)", () => {
      const result = SegmentReachSchema.safeParse({
        segment_name: "Test",
        active_count: 3,
        total_count: 10,
        ratio: 0.3,
      });
      expect(result.success).toBe(true);
    });
  });
});
