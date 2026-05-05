/**
 * Tests für BranchComparePanel.vue — Side-by-side-Compare-View für zwei Branches.
 *
 * useBranchComparison wird gemockt.
 * i18n: createI18n mit minimaler de-Locale (branchCompare-Keys).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";
import { createI18n } from "vue-i18n";
import type { BranchComparison } from "../../../contracts/branchComparisonContract";

// --- Mock useBranchComparison ---
const mockFetchComparison = vi.fn();
const mockReset = vi.fn();
const mockComparison = ref<BranchComparison | null>(null);
const mockLoading = ref(false);
const mockError = ref<string | null>(null);

vi.mock("../../../composables/useBranchComparison", () => ({
  useBranchComparison: () => ({
    comparison: mockComparison,
    loading: mockLoading,
    error: mockError,
    fetchComparison: mockFetchComparison,
    reset: mockReset,
  }),
}));

// --- Minimale i18n-Locale ---
const i18n = createI18n({
  legacy: false,
  locale: "de",
  messages: {
    de: {
      branchCompare: {
        title: "Branch-Vergleich",
        simulationLabel: "Simulation",
        branchA: "Branch A",
        branchB: "Branch B",
        deltas: {
          echoChamber: "ΔEcho-Chamber",
          clusters: "ΔCluster",
          bridgeAgents: "ΔBridge-Agents",
          avgEvidence: "ΔAvg-Evidence",
          contradictionRatio: "ΔContradiction",
          interactionDensity: "ΔInteraction-Density",
        },
        metrics: {
          echoChamberIndex: "Echo-Chamber-Index",
          clusterCount: "Cluster",
          bridgeAgents: "Bridge-Agents",
          totalAgents: "Gesamt-Agenten",
          totalInteractions: "Interaktionen",
          interactionDensity: "Interaktionsdichte",
          avgEvidencePerClaim: "Ø Evidence/Claim",
          claimsWithoutEvidenceRatio: "Claims ohne Evidence",
          contradictionRatio: "Widerspruchsrate",
          confidenceDistribution: "Konfidenz-Verteilung",
          personaReach: "Persona-Aktivierung",
          dominantClusters: "Dominante Cluster",
        },
        confidence: {
          low: "Niedrig",
          medium: "Mittel",
          high: "Hoch",
          verified: "Verifiziert",
        },
        clustersOnlyInA: "Nur in Branch A",
        clustersOnlyInB: "Nur in Branch B",
        clustersChanged: "Veränderte Cluster",
        empty: {
          sameBranches: "Bitte zwei verschiedene Branches wählen.",
          selectBranches: "Bitte zwei Branches auswählen.",
        },
        loading: "Vergleich wird geladen…",
        error: {
          generic: "Fehler beim Laden des Vergleichs",
        },
        completedAt: "Abgeschlossen",
      },
    },
  },
});

// --- Hilfsfunktion: valides BranchComparison-Stub ---
function makeValidComparison(): BranchComparison {
  const metrics = {
    echo_chamber_index: 0.4,
    cluster_count: 3,
    dominant_clusters: [],
    bridge_agent_ids: [1, 2],
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
      cluster_delta: 1,
      bridge_agents_delta: -2,
      confidence_distribution_delta: { low: 0, medium: 0, high: 0, verified: 0 },
      avg_evidence_delta: 0.3,
      contradiction_ratio_delta: -0.02,
      interaction_density_delta: 1.5,
      clusters_only_in_a: [
        { cluster_id: 10, size: 5, label: "Cluster A-only", member_count: 5 },
      ],
      clusters_only_in_b: [
        { cluster_id: 11, size: 3, label: "Cluster B-only", member_count: 3 },
      ],
      clusters_changed: [
        {
          cluster_id: 42,
          size_a: 5,
          size_b: 8,
          label_a: "Alte Gruppe",
          label_b: "Neue Gruppe",
        },
      ],
    },
  };
}

const defaultBranches = [
  { id: "branch-a", label: "Branch A (Kontrolle)" },
  { id: "branch-b", label: "Branch B (Variante)" },
];

// Import nach Mocks
import BranchComparePanel from "../BranchComparePanel.vue";

function mountPanel(
  props: Record<string, unknown> = {},
  options: Record<string, unknown> = {}
) {
  return mount(BranchComparePanel, {
    props: {
      simulationId: "sim-001",
      availableBranches: defaultBranches,
      ...props,
    },
    global: {
      plugins: [i18n],
      ...(options.global as Record<string, unknown>),
    },
  });
}

beforeEach(() => {
  mockComparison.value = null;
  mockLoading.value = false;
  mockError.value = null;
  mockFetchComparison.mockReset();
  mockReset.mockReset();
});

describe("BranchComparePanel", () => {
  describe("Statistik-Strip (6 Δ-Tiles)", () => {
    it("rendert alle 6 Δ-Tiles wenn Comparison vorhanden", async () => {
      mockComparison.value = makeValidComparison();
      const wrapper = mountPanel({
        defaultBranchA: "branch-a",
        defaultBranchB: "branch-b",
      });
      await flushPromises();

      const labels = wrapper.findAll(".delta-tile-label");
      const texts = labels.map((el) => el.text());
      expect(texts).toContain("ΔEcho-Chamber");
      expect(texts).toContain("ΔCluster");
      expect(texts).toContain("ΔBridge-Agents");
      expect(texts).toContain("ΔAvg-Evidence");
      expect(texts).toContain("ΔContradiction");
      expect(texts).toContain("ΔInteraction-Density");
    });

    it("formatiert positive Δ-Werte mit Vorzeichen", async () => {
      mockComparison.value = makeValidComparison();
      const wrapper = mountPanel({
        defaultBranchA: "branch-a",
        defaultBranchB: "branch-b",
      });
      await flushPromises();

      const values = wrapper.findAll(".delta-tile-value");
      const texts = values.map((el) => el.text());
      // echo_chamber_delta: 0.1 → "+0.100"
      expect(texts.some((t) => t.startsWith("+"))).toBe(true);
    });
  });

  describe("Branch-Karten (zweispaltig mit KPI-Block)", () => {
    it("rendert beide Branch-Karten mit KPI-Block", async () => {
      mockComparison.value = makeValidComparison();
      const wrapper = mountPanel({
        defaultBranchA: "branch-a",
        defaultBranchB: "branch-b",
      });
      await flushPromises();

      const cards = wrapper.findAll(".branch-card");
      expect(cards).toHaveLength(2);

      // KPI-Tiles prüfen
      const kpiLabels = wrapper.findAll(".kpi-label");
      expect(kpiLabels.length).toBeGreaterThanOrEqual(9 * 2); // 9 KPIs × 2 Karten
    });

    it("rendert Branch-IDs in den Karten-Headern", async () => {
      mockComparison.value = makeValidComparison();
      const wrapper = mountPanel({
        defaultBranchA: "branch-a",
        defaultBranchB: "branch-b",
      });
      await flushPromises();

      const html = wrapper.html();
      expect(html).toContain("branch-a");
      expect(html).toContain("branch-b");
    });
  });

  describe("Cluster-Listen", () => {
    it("rendert alle drei Cluster-Listen (only_a, only_b, changed)", async () => {
      mockComparison.value = makeValidComparison();
      const wrapper = mountPanel({
        defaultBranchA: "branch-a",
        defaultBranchB: "branch-b",
      });
      await flushPromises();

      expect(wrapper.find(".cluster-only-a").exists()).toBe(true);
      expect(wrapper.find(".cluster-only-b").exists()).toBe(true);
      expect(wrapper.find(".cluster-changed").exists()).toBe(true);

      // Cluster-Daten sichtbar
      const html = wrapper.html();
      expect(html).toContain("Cluster A-only");
      expect(html).toContain("Cluster B-only");
      expect(html).toContain("Alte Gruppe");
      expect(html).toContain("Neue Gruppe");
    });
  });

  describe("Branch-Selector-Wechsel", () => {
    it("initialer Watcher triggert fetchComparison mit beiden Branch-IDs", async () => {
      mountPanel({
        defaultBranchA: "branch-a",
        defaultBranchB: "branch-b",
      });
      await flushPromises();

      expect(mockFetchComparison).toHaveBeenCalledWith(
        "sim-001",
        "branch-a",
        "branch-b"
      );
    });

    it("fetchComparison wird NICHT aufgerufen bei leeren Branches", async () => {
      mountPanel({
        defaultBranchA: "",
        defaultBranchB: "",
      });
      await flushPromises();

      expect(mockFetchComparison).not.toHaveBeenCalled();
    });
  });

  describe("Empty-State bei gleichen Branches", () => {
    it("zeigt Hinweis wenn A === B", async () => {
      const wrapper = mountPanel({
        defaultBranchA: "branch-a",
        defaultBranchB: "branch-a",
      });
      await flushPromises();

      expect(wrapper.find(".compare-empty").exists()).toBe(true);
      expect(wrapper.find(".compare-empty").text()).toContain(
        "Bitte zwei verschiedene Branches wählen."
      );
      expect(mockFetchComparison).not.toHaveBeenCalled();
    });

    it("zeigt Hinweis wenn keine Branches gewählt", async () => {
      const wrapper = mountPanel({
        defaultBranchA: "",
        defaultBranchB: "",
      });
      await flushPromises();

      expect(wrapper.find(".compare-empty").exists()).toBe(true);
      expect(wrapper.find(".compare-empty").text()).toContain(
        "Bitte zwei Branches auswählen."
      );
    });
  });

  describe("Loading- und Error-State", () => {
    it("zeigt Spinner wenn loading=true", async () => {
      mockLoading.value = true;
      const wrapper = mountPanel({
        defaultBranchA: "branch-a",
        defaultBranchB: "branch-b",
      });
      await flushPromises();

      expect(wrapper.find(".compare-loading").exists()).toBe(true);
      expect(wrapper.find(".compare-spinner").exists()).toBe(true);
      expect(wrapper.find(".compare-loading").text()).toContain(
        "Vergleich wird geladen…"
      );
    });

    it("zeigt Error-Banner wenn error gesetzt", async () => {
      mockError.value = "Branch nicht gefunden";
      const wrapper = mountPanel({
        defaultBranchA: "branch-a",
        defaultBranchB: "branch-b",
      });
      await flushPromises();

      expect(wrapper.find(".compare-error").exists()).toBe(true);
      expect(wrapper.find(".compare-error").text()).toContain(
        "Fehler beim Laden des Vergleichs"
      );
      expect(wrapper.find(".compare-error").text()).toContain(
        "Branch nicht gefunden"
      );
    });
  });

  describe("i18n — keine hartkodierten Strings", () => {
    it("Branch-Selector-Labels kommen aus i18n", async () => {
      const wrapper = mountPanel({
        defaultBranchA: "branch-a",
        defaultBranchB: "branch-b",
      });
      await flushPromises();

      const html = wrapper.html();
      expect(html).toContain("Branch A");
      expect(html).toContain("Branch B");
      expect(html).toContain("Simulation");
    });

    it("Cluster-Listen-Titel kommen aus i18n", async () => {
      mockComparison.value = makeValidComparison();
      const wrapper = mountPanel({
        defaultBranchA: "branch-a",
        defaultBranchB: "branch-b",
      });
      await flushPromises();

      const html = wrapper.html();
      expect(html).toContain("Nur in Branch A");
      expect(html).toContain("Nur in Branch B");
      expect(html).toContain("Veränderte Cluster");
    });
  });
});
