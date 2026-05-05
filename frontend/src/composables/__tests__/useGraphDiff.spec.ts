/**
 * Tests für useGraphDiff — Composable für den Graph-Snapshot-Diff.
 *
 * Getestete Contracts:
 *   1. happy path: valide GraphDiff-Response → diff.value befüllt
 *   2. 404: error.value gesetzt, diff.value null
 *   3. Zod-Fehler: ungültige Struktur → error.value gesetzt
 *   4. reset(): alle Refs zurücksetzen
 *   5. Mehrfacher Aufruf: zweiter fetchDiff ersetzt ersten
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useGraphDiff } from "../useGraphDiff";

// --- Minimales valides GraphDiff-Objekt ---
function makeValidDiff() {
  return {
    graph_id: "graph-abc",
    snapshot_a_id: "snap-a",
    snapshot_b_id: "snap-b",
    created_at: "2026-05-05T10:00:00Z",
    comparison_type: "round-to-round",
    snapshot_a: {
      graph_id: "graph-abc",
      round_num: 1,
      snapshot_id: "snap-a",
      created_at: "2026-05-05T09:00:00Z",
      node_count: 5,
      edge_count: 3,
      edges: [],
      density: 0.3,
      cluster_count: 2,
      dominant_clusters: [],
      bridge_agents: [],
    },
    snapshot_b: {
      graph_id: "graph-abc",
      round_num: 2,
      snapshot_id: "snap-b",
      created_at: "2026-05-05T10:00:00Z",
      node_count: 6,
      edge_count: 4,
      edges: [],
      density: 0.35,
      cluster_count: 2,
      dominant_clusters: [],
      bridge_agents: [],
    },
    edges_added: [],
    edges_removed: [],
    edges_reinforced: [],
    edges_weakened: [],
    node_properties_changed: [],
    cluster_shifts: [],
    clusters_new: [],
    clusters_removed: [],
    bridge_agent_shifts: [],
    metrics: {
      total_edges_added: 0,
      total_edges_removed: 0,
      total_edges_reinforced: 0,
      total_edges_weakened: 0,
      avg_reinforcement_delta: 0.0,
      avg_weakening_delta: 0.0,
      density_delta: 0.05,
      node_properties_changed: 0,
      agents_changed_clusters: 0,
      clusters_new: 0,
      clusters_removed: 0,
      bridge_agents_joined: 0,
      bridge_agents_left: 0,
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

describe("useGraphDiff", () => {
  describe("happy path", () => {
    it("befüllt diff.value mit validem GraphDiff, kein error", async () => {
      const validDiff = makeValidDiff();
      vi.stubGlobal("fetch", mockFetch(validDiff));

      const { diff, loading, error, fetchDiff } = useGraphDiff();

      expect(loading.value).toBe(false);
      const promise = fetchDiff("graph-abc", "snap-a", "snap-b");
      expect(loading.value).toBe(true);
      await promise;

      expect(loading.value).toBe(false);
      expect(error.value).toBeNull();
      expect(diff.value).not.toBeNull();
      expect(diff.value?.graph_id).toBe("graph-abc");
      expect(diff.value?.comparison_type).toBe("round-to-round");
    });

    it("unwrappt json.data.diff-Envelope korrekt", async () => {
      const validDiff = makeValidDiff();
      vi.stubGlobal("fetch", mockFetch({ data: { diff: validDiff } }));

      const { diff, error, fetchDiff } = useGraphDiff();
      await fetchDiff("graph-abc", "snap-a", "snap-b");

      expect(error.value).toBeNull();
      expect(diff.value?.graph_id).toBe("graph-abc");
    });

    it("unwrappt json.diff-Envelope korrekt", async () => {
      const validDiff = makeValidDiff();
      vi.stubGlobal("fetch", mockFetch({ diff: validDiff }));

      const { diff, error, fetchDiff } = useGraphDiff();
      await fetchDiff("graph-abc", "snap-a", "snap-b");

      expect(error.value).toBeNull();
      expect(diff.value?.graph_id).toBe("graph-abc");
    });
  });

  describe("Fehlerszenarien", () => {
    it("404: error.value gesetzt, diff.value null", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValueOnce({
          ok: false,
          status: 404,
          json: vi.fn().mockResolvedValueOnce({ error: { message: "Nicht gefunden" } }),
        })
      );

      const { diff, error, fetchDiff } = useGraphDiff();
      await fetchDiff("graph-abc", "snap-a", "snap-b");

      expect(diff.value).toBeNull();
      expect(error.value).toBe("Nicht gefunden");
    });

    it("404 ohne body: Fallback-Meldung", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValueOnce({
          ok: false,
          status: 404,
          json: vi.fn().mockRejectedValueOnce(new Error("no json")),
        })
      );

      const { diff, error, fetchDiff } = useGraphDiff();
      await fetchDiff("graph-abc", "snap-a", "snap-b");

      expect(diff.value).toBeNull();
      expect(error.value).toBe("Snapshot nicht gefunden");
    });

    it("422: error.value gesetzt", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValueOnce({
          ok: false,
          status: 422,
          json: vi.fn().mockRejectedValueOnce(new Error("no json")),
        })
      );

      const { diff, error, fetchDiff } = useGraphDiff();
      await fetchDiff("graph-abc", "snap-a", "snap-b");

      expect(diff.value).toBeNull();
      expect(error.value).toBe("Snapshot unvollständig");
    });

    it("Zod-Fehler: Server liefert ungültige Struktur → error.value mit ZodError-Message", async () => {
      const invalidPayload = { graph_id: "x", comparison_type: "invalid-type" };
      vi.stubGlobal("fetch", mockFetch(invalidPayload));

      const { diff, error, fetchDiff } = useGraphDiff();
      await fetchDiff("graph-abc", "snap-a", "snap-b");

      expect(diff.value).toBeNull();
      expect(error.value).toBeTruthy();
      expect(typeof error.value).toBe("string");
    });

    it("Network-Fehler: error.value gesetzt", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockRejectedValueOnce(new Error("Network failure"))
      );

      const { diff, error, fetchDiff } = useGraphDiff();
      await fetchDiff("graph-abc", "snap-a", "snap-b");

      expect(diff.value).toBeNull();
      expect(error.value).toBe("Network failure");
    });
  });

  describe("reset()", () => {
    it("setzt alle Refs zurück", async () => {
      const validDiff = makeValidDiff();
      vi.stubGlobal("fetch", mockFetch(validDiff));

      const { diff, loading, error, fetchDiff, reset } = useGraphDiff();
      await fetchDiff("graph-abc", "snap-a", "snap-b");

      expect(diff.value).not.toBeNull();

      reset();

      expect(diff.value).toBeNull();
      expect(error.value).toBeNull();
      expect(loading.value).toBe(false);
    });
  });

  describe("mehrfacher Aufruf", () => {
    it("zweiter fetchDiff ersetzt ersten", async () => {
      const diffA = { ...makeValidDiff(), graph_id: "graph-A" };
      const diffB = { ...makeValidDiff(), graph_id: "graph-B" };

      vi.stubGlobal(
        "fetch",
        vi.fn()
          .mockResolvedValueOnce({
            ok: true,
            status: 200,
            json: vi.fn().mockResolvedValueOnce(diffA),
          })
          .mockResolvedValueOnce({
            ok: true,
            status: 200,
            json: vi.fn().mockResolvedValueOnce(diffB),
          })
      );

      const { diff, error, fetchDiff } = useGraphDiff();
      await fetchDiff("graph-A", "snap-a", "snap-b");
      expect(diff.value?.graph_id).toBe("graph-A");

      await fetchDiff("graph-B", "snap-a", "snap-b");
      expect(diff.value?.graph_id).toBe("graph-B");
      expect(error.value).toBeNull();
    });
  });
});
