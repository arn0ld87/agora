/**
 * Tests für GraphDiffPanel.vue — Diff-View für Graph-Snapshots.
 *
 * useGraphDiff wird gemockt. GraphCanvas wird als Stub-Komponente gerendert.
 * i18n: createI18n mit minimaler de-Locale.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";
import { createI18n } from "vue-i18n";
import type { GraphDiff } from "../../../contracts/graphDiffContract";

// --- Mock useGraphDiff ---
const mockFetchDiff = vi.fn();
const mockReset = vi.fn();
const mockDiff = ref<GraphDiff | null>(null);
const mockLoading = ref(false);
const mockError = ref<string | null>(null);

vi.mock("../../../composables/useGraphDiff", () => ({
  useGraphDiff: () => ({
    diff: mockDiff,
    loading: mockLoading,
    error: mockError,
    fetchDiff: mockFetchDiff,
    reset: mockReset,
  }),
}));

// --- Mock GraphCanvas ---
vi.mock("../GraphCanvas.vue", () => ({
  default: {
    name: "GraphCanvas",
    template: '<div class="graph-canvas-stub"></div>',
    props: ["graphData", "entityTypes", "loading"],
  },
}));

// --- Minimale i18n-Locale ---
const i18n = createI18n({
  legacy: false,
  locale: "de",
  messages: {
    de: {
      graphDiff: {
        title: "Graph-Snapshot-Vergleich",
        snapshotA: "Snapshot A",
        snapshotB: "Snapshot B",
        statsNodes: "ΔKnoten",
        statsEdges: "ΔKanten",
        statsClusters: "ΔCluster",
        statsDensity: "ΔDichte",
        legend: {
          added: "Hinzugefügt",
          removed: "Entfernt",
          reinforced: "Verstärkt",
          weakened: "Geschwächt",
        },
        clustersOnlyInA: "Nur in Snapshot A",
        clustersOnlyInB: "Nur in Snapshot B",
        clustersChanged: "Veränderte Cluster",
        empty: {
          sameSnapshots: "Bitte zwei verschiedene Snapshots wählen.",
        },
        loading: "Vergleich wird geladen…",
        error: {
          generic: "Fehler beim Laden des Vergleichs",
        },
      },
    },
  },
});

// --- Hilfsfunktion: validen GraphDiff-Stub erstellen ---
function makeValidDiff(): GraphDiff {
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
      node_count: 7,
      edge_count: 5,
      edges: [],
      density: 0.4,
      cluster_count: 3,
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
      total_edges_added: 2,
      total_edges_removed: 0,
      total_edges_reinforced: 0,
      total_edges_weakened: 0,
      avg_reinforcement_delta: 0.0,
      avg_weakening_delta: 0.0,
      density_delta: 0.1,
      node_properties_changed: 0,
      agents_changed_clusters: 0,
      clusters_new: 1,
      clusters_removed: 0,
      bridge_agents_joined: 0,
      bridge_agents_left: 0,
    },
  };
}

const defaultSnapshots = [
  { id: "snap-a", label: "Runde 1" },
  { id: "snap-b", label: "Runde 2" },
];

// Import nach Mocks
import GraphDiffPanel from "../GraphDiffPanel.vue";

function mountPanel(
  props: Record<string, unknown> = {},
  options: Record<string, unknown> = {}
) {
  return mount(GraphDiffPanel, {
    props: {
      graphId: "graph-abc",
      availableSnapshots: defaultSnapshots,
      ...props,
    },
    global: {
      plugins: [i18n],
      ...(options.global as Record<string, unknown>),
    },
  });
}

beforeEach(() => {
  mockDiff.value = null;
  mockLoading.value = false;
  mockError.value = null;
  mockFetchDiff.mockReset();
  mockReset.mockReset();
});

describe("GraphDiffPanel", () => {
  describe("Statistik-Strip", () => {
    it("zeigt Statistik-Strip wenn Diff vorhanden", async () => {
      mockDiff.value = makeValidDiff();
      const wrapper = mountPanel({
        defaultSnapshotA: "snap-a",
        defaultSnapshotB: "snap-b",
      });
      await flushPromises();

      expect(wrapper.find(".diff-stats").exists()).toBe(true);
      const statLabels = wrapper.findAll(".diff-stat-label");
      const texts = statLabels.map((el) => el.text());
      expect(texts).toContain("ΔKnoten");
      expect(texts).toContain("ΔKanten");
      expect(texts).toContain("ΔCluster");
      expect(texts).toContain("ΔDichte");
    });

    it("zeigt Delta-Werte für Nodes positiv formatiert", async () => {
      mockDiff.value = makeValidDiff();
      const wrapper = mountPanel({
        defaultSnapshotA: "snap-a",
        defaultSnapshotB: "snap-b",
      });
      await flushPromises();

      const statValues = wrapper.findAll(".diff-stat-value");
      // node_count: 7 - 5 = +2
      const nodeStatText = statValues[0]?.text() ?? "";
      expect(nodeStatText).toBe("+2");
    });
  });

  describe("Snapshot-Selektor", () => {
    it("rendert zwei select-Elemente", () => {
      const wrapper = mountPanel();
      const selects = wrapper.findAll("select.diff-select");
      expect(selects).toHaveLength(2);
    });

    it("Selektor-Wechsel triggert fetchDiff", async () => {
      const wrapper = mountPanel({
        defaultSnapshotA: "snap-a",
        defaultSnapshotB: "snap-b",
      });
      await flushPromises();

      // fetchDiff sollte beim initialen Watcher bereits aufgerufen worden sein
      expect(mockFetchDiff).toHaveBeenCalledWith("graph-abc", "snap-a", "snap-b");
    });

    it("fetchDiff wird NICHT aufgerufen bei leeren Snapshots", async () => {
      mountPanel({
        defaultSnapshotA: "",
        defaultSnapshotB: "",
      });
      await flushPromises();

      expect(mockFetchDiff).not.toHaveBeenCalled();
    });
  });

  describe("Empty-State bei gleichen Snapshots", () => {
    it("zeigt Hinweis wenn A === B", async () => {
      const wrapper = mountPanel({
        defaultSnapshotA: "snap-a",
        defaultSnapshotB: "snap-a",
      });
      await flushPromises();

      expect(wrapper.find(".diff-empty").exists()).toBe(true);
      expect(wrapper.find(".diff-empty").text()).toContain(
        "Bitte zwei verschiedene Snapshots wählen."
      );
      expect(mockFetchDiff).not.toHaveBeenCalled();
    });
  });

  describe("Loading-State", () => {
    it("zeigt Spinner wenn loading=true", async () => {
      mockLoading.value = true;
      const wrapper = mountPanel({
        defaultSnapshotA: "snap-a",
        defaultSnapshotB: "snap-b",
      });
      await flushPromises();

      expect(wrapper.find(".diff-loading").exists()).toBe(true);
      expect(wrapper.find(".diff-spinner").exists()).toBe(true);
      expect(wrapper.find(".diff-loading").text()).toContain(
        "Vergleich wird geladen…"
      );
    });
  });

  describe("Error-State", () => {
    it("zeigt Error-Banner wenn error gesetzt", async () => {
      mockError.value = "Snapshot nicht gefunden";
      const wrapper = mountPanel({
        defaultSnapshotA: "snap-a",
        defaultSnapshotB: "snap-b",
      });
      await flushPromises();

      expect(wrapper.find(".diff-error").exists()).toBe(true);
      expect(wrapper.find(".diff-error").text()).toContain(
        "Fehler beim Laden des Vergleichs"
      );
      expect(wrapper.find(".diff-error").text()).toContain(
        "Snapshot nicht gefunden"
      );
    });
  });

  describe("i18n — keine hartkodierten Strings", () => {
    it("Snapshot-Label-Texte kommen aus i18n", async () => {
      const wrapper = mountPanel({
        defaultSnapshotA: "snap-a",
        defaultSnapshotB: "snap-b",
      });
      await flushPromises();

      const html = wrapper.html();
      // Die i18n-Texte sollen vorhanden sein
      expect(html).toContain("Snapshot A");
      expect(html).toContain("Snapshot B");
    });

    it("Legende-Labels kommen aus i18n wenn Diff vorhanden", async () => {
      mockDiff.value = makeValidDiff();
      const wrapper = mountPanel({
        defaultSnapshotA: "snap-a",
        defaultSnapshotB: "snap-b",
      });
      await flushPromises();

      const html = wrapper.html();
      expect(html).toContain("Hinzugefügt");
      expect(html).toContain("Entfernt");
      expect(html).toContain("Verstärkt");
      expect(html).toContain("Geschwächt");
    });
  });
});
