/**
 * Tests für useBranchComparison — Composable für den Branch-Compare-Endpunkt.
 *
 * Getestete Contracts:
 *   1. happy path (200) → comparison.value befüllt
 *   2. 404 NOT_FOUND → error.value enthält Backend-Message, comparison.value === null
 *   3. 422 INCOMPLETE_STATE → error.value enthält INCOMPLETE-Message
 *   4. 400 VALIDATION_FAILED → error.value enthält VALIDATION-Message
 *   5. Zod-Fehler bei ungültiger Server-Response → error.value enthält ZodError-Message
 *   6. reset() setzt alle Refs zurück
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useBranchComparison } from "../useBranchComparison";

// --- Minimales valides BranchComparison-Objekt ---
function makeValidComparison() {
  const metrics = {
    echo_chamber_index: 0.4,
    cluster_count: 3,
    dominant_clusters: [],
    bridge_agent_ids: [],
    total_agents: 100,
    total_interactions: 500,
    interaction_density: 5.0,
    confidence_distribution: { low: 10, medium: 20, high: 15, verified: 5 },
    avg_evidence_per_claim: 2.5,
    claims_without_evidence_ratio: 0.1,
    contradiction_ratio: 0.05,
    persona_reach: {},
  };
  return {
    simulation_id: "sim-001",
    branch_a_id: "branch-a",
    branch_b_id: "branch-b",
    created_at: "2026-05-05T10:00:00Z",
    branch_a_completed_at: "2026-05-05T08:00:00Z",
    branch_b_completed_at: "2026-05-05T09:00:00Z",
    metrics_a: { ...metrics },
    metrics_b: { ...metrics, echo_chamber_index: 0.5 },
    deltas: {
      echo_chamber_delta: 0.1,
      cluster_delta: 0,
      bridge_agents_delta: 0,
      confidence_distribution_delta: { low: 0, medium: 0, high: 0, verified: 0 },
      avg_evidence_delta: 0.0,
      contradiction_ratio_delta: 0.0,
      interaction_density_delta: 0.0,
      clusters_only_in_a: [],
      clusters_only_in_b: [],
      clusters_changed: [],
    },
  };
}

function mockFetch(response: unknown, status = 200) {
  return vi.fn().mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValueOnce(response),
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("useBranchComparison", () => {
  describe("happy path", () => {
    it("200: befüllt comparison.value mit validem BranchComparison, kein error", async () => {
      const valid = makeValidComparison();
      vi.stubGlobal("fetch", mockFetch(valid));

      const { comparison, loading, error, fetchComparison } =
        useBranchComparison();

      expect(loading.value).toBe(false);
      const promise = fetchComparison("sim-001", "branch-a", "branch-b");
      expect(loading.value).toBe(true);
      await promise;

      expect(loading.value).toBe(false);
      expect(error.value).toBeNull();
      expect(comparison.value).not.toBeNull();
      expect(comparison.value?.simulation_id).toBe("sim-001");
      expect(comparison.value?.branch_a_id).toBe("branch-a");
    });

    it("unwrappt json.data.comparison-Envelope korrekt", async () => {
      const valid = makeValidComparison();
      vi.stubGlobal("fetch", mockFetch({ data: { comparison: valid } }));

      const { comparison, error, fetchComparison } = useBranchComparison();
      await fetchComparison("sim-001", "branch-a", "branch-b");

      expect(error.value).toBeNull();
      expect(comparison.value?.simulation_id).toBe("sim-001");
    });

    it("unwrappt json.comparison-Envelope korrekt", async () => {
      const valid = makeValidComparison();
      vi.stubGlobal("fetch", mockFetch({ comparison: valid }));

      const { comparison, error, fetchComparison } = useBranchComparison();
      await fetchComparison("sim-001", "branch-a", "branch-b");

      expect(error.value).toBeNull();
      expect(comparison.value?.simulation_id).toBe("sim-001");
    });
  });

  describe("Fehlerszenarien", () => {
    it("404 NOT_FOUND: error.value enthält Backend-Message, comparison.value === null", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValueOnce({
          ok: false,
          status: 404,
          json: vi
            .fn()
            .mockResolvedValueOnce({
              error: { message: "Branch nicht gefunden" },
            }),
        })
      );

      const { comparison, error, fetchComparison } = useBranchComparison();
      await fetchComparison("sim-001", "branch-a", "branch-b");

      expect(comparison.value).toBeNull();
      expect(error.value).toBe("Branch nicht gefunden");
    });

    it("422 INCOMPLETE_STATE: error.value enthält INCOMPLETE-Message", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValueOnce({
          ok: false,
          status: 422,
          json: vi
            .fn()
            .mockResolvedValueOnce({
              error: {
                message: "Branch-Simulation unvollständig: branch-b ist noch nicht fertig.",
              },
            }),
        })
      );

      const { comparison, error, fetchComparison } = useBranchComparison();
      await fetchComparison("sim-001", "branch-a", "branch-b");

      expect(comparison.value).toBeNull();
      expect(error.value).toContain("unvollständig");
    });

    it("400 VALIDATION_FAILED: error.value enthält VALIDATION-Message", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValueOnce({
          ok: false,
          status: 400,
          json: vi
            .fn()
            .mockResolvedValueOnce({
              error: { message: "branch_a_id und branch_b_id müssen verschieden sein" },
            }),
        })
      );

      const { comparison, error, fetchComparison } = useBranchComparison();
      await fetchComparison("sim-001", "branch-x", "branch-x");

      expect(comparison.value).toBeNull();
      expect(error.value).toContain("verschieden");
    });

    it("Zod-Fehler: Server liefert ungültige Struktur → error.value enthält ZodError-Message", async () => {
      const invalid = {
        simulation_id: "sim-001",
        // branch_a_id fehlt, ungültige Struktur
        completely_wrong: true,
      };
      vi.stubGlobal("fetch", mockFetch(invalid));

      const { comparison, error, fetchComparison } = useBranchComparison();
      await fetchComparison("sim-001", "branch-a", "branch-b");

      expect(comparison.value).toBeNull();
      expect(error.value).toBeTruthy();
      expect(typeof error.value).toBe("string");
    });

    it("Network-Fehler: error.value gesetzt", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockRejectedValueOnce(new Error("Network failure"))
      );

      const { comparison, error, fetchComparison } = useBranchComparison();
      await fetchComparison("sim-001", "branch-a", "branch-b");

      expect(comparison.value).toBeNull();
      expect(error.value).toBe("Network failure");
    });
  });

  describe("reset()", () => {
    it("setzt alle Refs zurück auf Ausgangszustand", async () => {
      const valid = makeValidComparison();
      vi.stubGlobal("fetch", mockFetch(valid));

      const { comparison, loading, error, fetchComparison, reset } =
        useBranchComparison();
      await fetchComparison("sim-001", "branch-a", "branch-b");

      expect(comparison.value).not.toBeNull();

      reset();

      expect(comparison.value).toBeNull();
      expect(error.value).toBeNull();
      expect(loading.value).toBe(false);
    });
  });
});
