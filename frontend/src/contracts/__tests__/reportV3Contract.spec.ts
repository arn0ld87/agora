/**
 * Zod-Spiegel-Drift-Test gegen den Backend-Vertrag (ReportV3).
 *
 * Sample-Payload spiegelt backend/tests/contracts/test_report_v3_contract.py
 * (`test_minimal_report_v3_roundtrip`). Wenn Pydantic-Modelle wandern,
 * muss dieser Test brechen, bis der Zod-Spiegel nachgezogen ist.
 * M11.8c.
 */
import { describe, it, expect } from "vitest";
import {
  parseReportV3,
  ReportV3Schema,
  ReportModeSchema,
  ClaimSchema,
  ThresholdSchema,
  HypothesisSchema,
  PersonaV3Schema,
} from "../reportV3Contract";
import reportV3Json from "../../../../schemas/report-v3.schema.json";

function propertyKeys(schema: { properties?: Record<string, unknown> }) {
  return Object.keys(schema.properties ?? {}).sort();
}

function shapeKeys(schema: { shape: Record<string, unknown> }) {
  return Object.keys(schema.shape).sort();
}

const EVIDENCE_ID = "ev_00000000000000000000000000000001";

const MINIMAL_REPORT_V3 = {
  schema_version: 4,
  report_id: "rep-001",
  generated_at: "2026-05-09T12:00:00Z",
  report_mode: "balanced",
  evidence_index: {
    [EVIDENCE_ID]: {
      evidence_id: EVIDENCE_ID,
      producer_key: "report-v4-contract-fixture",
      type: "graph_fact",
      source: "contract-fixture",
      snippet: "Vertraglich gebundene Evidence.",
      source_kind: "graph_relation",
    },
  },
  personas: [
    {
      id: "p1",
      voice_register: "formal-de",
      alter_range: "40–55",
      beruf: "Geschäftsführer",
      region: "Schweiz",
      needs: ["Zuverlässigkeit", "Sicherheit"],
      values: ["Qualität"],
      evidence_refs: [EVIDENCE_ID],
    },
  ],
  claims: [
    {
      id: "c1",
      statement: "Sicherheitsbedenken sind der primäre Hemmfaktor.",
      evidence_refs: [EVIDENCE_ID],
      confidence: "high",
      persona_ids: ["p1"],
      aggregation_basis: "persona",
    },
  ],
  data_gaps: [
    {
      id: "dg1",
      beschreibung: "Keine Daten zur Preisbereitschaft vorhanden.",
      severity: "medium",
      suggested_fixes: ["A/B-Test durchführen", "Marktforschung beauftragen"],
    },
  ],
  hypotheses: [
    {
      id: "hyp1",
      hypothesis_text: "Preisbereitschaft könnte segmentabhängig variieren.",
      rationale: "Keine harte Evidence im Seed-Korpus.",
      suggested_evidence: ["Preisinterviews"],
      confidence_score: 0.25,
    },
  ],
};

describe("ReportV3Schema (Zod-Spiegel)", () => {
  it("parses the canonical Backend round-trip payload", () => {
    const result = parseReportV3(MINIMAL_REPORT_V3);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.schema_version).toBe(4);
      expect(result.data.personas[0].voice_register).toBe("formal-de");
      expect(result.data.claims[0].evidence_refs).toEqual([EVIDENCE_ID]);
      expect(result.data.data_gaps[0].severity).toBe("medium");
      expect(result.data.hypotheses[0].suggested_evidence).toEqual([
        "Preisinterviews",
      ]);
    }
  });

  it("rejects schema_version=3 (Literal[4] enforced)", () => {
    const bad = { ...MINIMAL_REPORT_V3, schema_version: 3 };
    expect(ReportV3Schema.safeParse(bad).success).toBe(false);
  });

  it("rejects extra fields (extra=forbid)", () => {
    const bad = { ...MINIMAL_REPORT_V3, unbekannt: "xyz" };
    expect(ReportV3Schema.safeParse(bad).success).toBe(false);
  });

  it("rejects Claim without evidence_refs (min 1 required)", () => {
    const badClaim = {
      id: "c1",
      statement: "Dieser Claim ist ausreichend lang.",
      evidence_refs: [],
      confidence: "medium",
      aggregation_basis: "persona",
    };
    expect(ClaimSchema.safeParse(badClaim).success).toBe(false);
  });

  // Issue #1160 A: confidence_scope trennt Simulationskonsens von
  // Quellenbindung. Das Feld ist optional, weil report-v3.json aus der Zeit
  // davor es nicht traegt — "nicht erfasst" darf nicht stillschweigend zu
  // "simulation_consensus" werden.
  it("akzeptiert einen Claim ohne confidence_scope (Bestandsartefakt)", () => {
    const legacyClaim = {
      id: "c1",
      statement: "Dieser Claim ist ausreichend lang.",
      evidence_refs: [EVIDENCE_ID],
      confidence: "medium",
      aggregation_basis: "persona",
    };
    const parsed = ClaimSchema.safeParse(legacyClaim);
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.confidence_scope ?? null).toBe(null);
    }
  });

  it("akzeptiert die drei Geltungsbereiche und weist andere ab", () => {
    const base = {
      id: "c1",
      statement: "Dieser Claim ist ausreichend lang.",
      evidence_refs: [EVIDENCE_ID],
      confidence: "high",
      aggregation_basis: "persona",
    };
    for (const scope of ["simulation_consensus", "evidence", "empirical"]) {
      expect(ClaimSchema.safeParse({ ...base, confidence_scope: scope }).success).toBe(true);
    }
    expect(
      ClaimSchema.safeParse({ ...base, confidence_scope: "gefuehlt" }).success,
    ).toBe(false);
  });

  // Issue #1160 E: operative Zahlen tragen ihre Herkunft mit.
  it("akzeptiert eine operative Zahl mit ausgewiesener Herkunft", () => {
    const parsed = ThresholdSchema.safeParse({
      id: "thr_01",
      label: "Traffic-Baseline",
      value: 90,
      unit: "percent",
      purpose: "baseline",
      origin: "document_requirement",
    });
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      // Im Zweifel unbelegt — nicht belegt.
      expect(parsed.data.evidence_status).toBe("heuristic");
    }
  });

  it("weist eine als belegt markierte Zahl ohne Beleg ab", () => {
    // Spiegelt Threshold.verified_needs_an_evidence_ref im Backend: eine Zahl
    // als belegt auszuweisen, ohne einen Beleg zu nennen, ist genau die
    // Behauptung, die #1160 E adressiert.
    const result = ThresholdSchema.safeParse({
      id: "thr_01",
      label: "Traffic-Baseline",
      value: 90,
      unit: "percent",
      purpose: "baseline",
      origin: "empirical_data",
      evidence_status: "verified",
      evidence_refs: [],
    });
    expect(result.success).toBe(false);

    expect(
      ThresholdSchema.safeParse({
        id: "thr_01",
        label: "Traffic-Baseline",
        value: 90,
        unit: "percent",
        purpose: "baseline",
        origin: "empirical_data",
        evidence_status: "verified",
        evidence_refs: [EVIDENCE_ID],
      }).success,
    ).toBe(true);
  });

  it("weist eine erfundene Herkunft ab", () => {
    expect(
      ThresholdSchema.safeParse({
        id: "thr_01",
        label: "Traffic-Baseline",
        value: 90,
        unit: "percent",
        purpose: "baseline",
        origin: "bauchgefuehl",
      }).success,
    ).toBe(false);
  });

  // Issue #1343: kind trennt operative Mengen von Datumsangaben. Aus
  // „15. Oktober 2026" entstand sonst value=15.0 / unit="October".
  it("akzeptiert ein Bestandsartefakt ohne kind als numerische Menge", () => {
    const parsed = ThresholdSchema.safeParse({
      id: "thr_01",
      label: "Traffic-Baseline",
      value: 90,
      unit: "percent",
      purpose: "baseline",
      origin: "document_requirement",
    });
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      // „Nicht erfasst" bleibt null — kein stillschweigendes quantity.
      expect(parsed.data.kind).toBe(null);
    }
  });

  it("akzeptiert eine Datumsangabe nur mit ISO-Wert und ohne Einheit", () => {
    const parsed = ThresholdSchema.safeParse({
      id: "production_start",
      label: "Produktivstart",
      kind: "date",
      value: "2026-10-15",
      purpose: "target",
      origin: "document_requirement",
    });
    expect(parsed.success).toBe(true);
  });

  it("weist kind=date mit Nicht-ISO-Wert ab", () => {
    expect(
      ThresholdSchema.safeParse({
        id: "production_start",
        label: "Produktivstart",
        kind: "date",
        value: "15. Oktober 2026",
        purpose: "target",
        origin: "document_requirement",
      }).success,
    ).toBe(false);
  });

  it("weist kind=date mit Einheit ab — ein Datum ist keine Menge", () => {
    expect(
      ThresholdSchema.safeParse({
        id: "production_start",
        label: "Produktivstart",
        kind: "date",
        value: "2026-10-15",
        unit: "days",
        purpose: "target",
        origin: "document_requirement",
      }).success,
    ).toBe(false);
  });

  it("weist einen Monatsnamen als Einheit ab (#1343)", () => {
    for (const unit of ["October", "Oktober"]) {
      expect(
        ThresholdSchema.safeParse({
          id: "planungsmeilenstein_15_oktober",
          label: "Planungsmeilenstein",
          value: 15,
          unit,
          purpose: "target",
          origin: "simulation_proposal",
        }).success,
      ).toBe(false);
    }
  });

  it("weist einen Textwert ohne Datumform bei numerischem Threshold ab", () => {
    expect(
      ThresholdSchema.safeParse({
        id: "thr_01",
        label: "Traffic-Baseline",
        value: "42 Prozent",
        unit: "percent",
        purpose: "baseline",
        origin: "document_requirement",
      }).success,
    ).toBe(false);
  });

  // Review PR #1379, Blocker 1: Das Muster allein lässt unmögliche Daten
  // durch — der Spiegel liest Jahr/Monat/Tag, erzeugt über UTC und
  // vergleicht alle drei Komponenten zurück; dazu dieselbe
  // Plausibilitätsgrenze (1900–2100) wie der Backend-Parser.
  it("weist unmögliche Kalenderdaten ab", () => {
    for (const value of ["2026-02-30", "2026-13-01", "2026-02-29"]) {
      expect(
        ThresholdSchema.safeParse({
          id: "production_start",
          label: "Produktivstart",
          kind: "date",
          value,
          purpose: "target",
          origin: "document_requirement",
        }).success,
      ).toBe(false);
    }
  });

  it("akzeptiert einen echten Schalttag als Kalenderdatum", () => {
    expect(
      ThresholdSchema.safeParse({
        id: "production_start",
        label: "Produktivstart",
        kind: "date",
        value: "2028-02-29",
        purpose: "target",
        origin: "document_requirement",
      }).success,
    ).toBe(true);
  });

  it("weist Jahreswerte außerhalb der Plausibilitätsgrenze ab", () => {
    for (const value of ["1899-12-31", "2101-01-01"]) {
      expect(
        ThresholdSchema.safeParse({
          id: "production_start",
          label: "Produktivstart",
          kind: "date",
          value,
          purpose: "target",
          origin: "document_requirement",
        }).success,
      ).toBe(false);
    }
  });

  // Review PR #1379, Blocker 2: numerische Strings werden wie vor #1343 zu
  // Zahlen umgewandelt — echte Datumsstrings bleiben Strings.
  it("wandelt numerische Strings wie das Backend in Zahlen um", () => {
    const parsed = ThresholdSchema.safeParse({
      id: "thr_01",
      label: "Traffic-Baseline",
      value: "90",
      unit: "percent",
      purpose: "baseline",
      origin: "document_requirement",
    });
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.value).toBe(90);
      expect(typeof parsed.data.value).toBe("number");
    }
  });

  it("lässt Datumsstrings als Strings", () => {
    const parsed = ThresholdSchema.safeParse({
      id: "production_start",
      label: "Produktivstart",
      kind: "date",
      value: "2026-10-15",
      purpose: "target",
      origin: "document_requirement",
    });
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.value).toBe("2026-10-15");
    }
  });

  it("rejects Claim with invalid confidence value", () => {
    const badClaim = {
      id: "c1",
      statement: "Dieser Claim ist ausreichend lang.",
      evidence_refs: ["ev-001"],
      confidence: "ultra",
      aggregation_basis: "persona",
    };
    expect(ClaimSchema.safeParse(badClaim).success).toBe(false);
  });

  it("rejects Persona without voice_register", () => {
    const badPersona = {
      id: "p1",
      alter_range: "25–35",
      beruf: "UX-Designer",
      region: "Berlin",
    };
    expect(PersonaV3Schema.safeParse(badPersona).success).toBe(false);
  });

  it("rejects Persona with unknown voice_register", () => {
    const badPersona = {
      id: "p1",
      voice_register: "englisch-cool",
      alter_range: "25–35",
      beruf: "UX-Designer",
      region: "Berlin",
    };
    expect(PersonaV3Schema.safeParse(badPersona).success).toBe(false);
  });

  it("contains all 14 section list keys in schema output", () => {
    const schema = ReportV3Schema.shape;
    const expected = [
      "personas",
      "segments",
      "claims",
      "multipliers",
      "friction_points",
      "trust_signals",
      "change_recommendations",
      "project_impacts",
      "positioning_variants",
      "content_ideas",
      "data_gaps",
      "hypotheses",
      // Slice 5 (Issue #497)
      "red_team_findings",
      "model_attribution",
    ];
    for (const key of expected) {
      expect(key in schema).toBe(true);
    }
  });

  it("spiegelt die ReportV3-Backend-JSON-Schema-Properties", () => {
    expect(shapeKeys(ReportV3Schema)).toEqual(propertyKeys(reportV3Json));
    expect(shapeKeys(PersonaV3Schema)).toEqual(propertyKeys(reportV3Json.$defs.Persona));
    expect(shapeKeys(ClaimSchema)).toEqual(propertyKeys(reportV3Json.$defs.Claim));
    expect(shapeKeys(HypothesisSchema)).toEqual(propertyKeys(reportV3Json.$defs.Hypothesis));
    expect(shapeKeys(ThresholdSchema)).toEqual(propertyKeys(reportV3Json.$defs.Threshold));
  });

  it("report_mode defaults to 'balanced' when absent", () => {
    const withoutMode = {
      schema_version: 4,
      report_id: "r-no-mode",
      generated_at: "2026-05-11T00:00:00Z",
    };
    const result = ReportV3Schema.safeParse(withoutMode);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.report_mode).toBe("balanced");
    }
  });

  it("report_mode accepts strict and explorative", () => {
    for (const mode of ["strict", "explorative"] as const) {
      const result = ReportModeSchema.safeParse(mode);
      expect(result.success).toBe(true);
    }
  });

  it("report_mode rejects unknown values", () => {
    const result = ReportModeSchema.safeParse("nuclear");
    expect(result.success).toBe(false);
  });

  it("parses minimal report with empty section lists", () => {
    const minimal = {
      schema_version: 4,
      report_id: "r-empty",
      generated_at: "2026-05-09T00:00:00Z",
    };
    const result = ReportV3Schema.safeParse(minimal);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.personas).toEqual([]);
      expect(result.data.claims).toEqual([]);
      expect(result.data.data_gaps).toEqual([]);
      expect(result.data.hypotheses).toEqual([]);
      expect(result.data.red_team_findings).toEqual([]);
    }
  });
});
