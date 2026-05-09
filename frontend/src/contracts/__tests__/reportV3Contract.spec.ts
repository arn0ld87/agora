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
  ClaimSchema,
  PersonaV3Schema,
} from "../reportV3Contract";

const MINIMAL_REPORT_V3 = {
  schema_version: 3,
  report_id: "rep-001",
  generated_at: "2026-05-09T12:00:00Z",
  personas: [
    {
      id: "p1",
      voice_register: "formal-de",
      alter_range: "40–55",
      beruf: "Geschäftsführer",
      region: "Schweiz",
      needs: ["Zuverlässigkeit", "Sicherheit"],
      values: ["Qualität"],
      evidence_refs: ["ev-001"],
    },
  ],
  claims: [
    {
      id: "c1",
      statement: "Sicherheitsbedenken sind der primäre Hemmfaktor.",
      evidence_refs: ["ev-001"],
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
};

describe("ReportV3Schema (Zod-Spiegel)", () => {
  it("parses the canonical Backend round-trip payload", () => {
    const result = parseReportV3(MINIMAL_REPORT_V3);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.schema_version).toBe(3);
      expect(result.data.personas[0].voice_register).toBe("formal-de");
      expect(result.data.claims[0].evidence_refs).toEqual(["ev-001"]);
      expect(result.data.data_gaps[0].severity).toBe("medium");
    }
  });

  it("rejects schema_version=2 (Literal[3] enforced)", () => {
    const bad = { ...MINIMAL_REPORT_V3, schema_version: 2 };
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

  it("contains all 11 section list keys in schema output", () => {
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
    ];
    for (const key of expected) {
      expect(key in schema).toBe(true);
    }
  });

  it("parses minimal report with empty section lists", () => {
    const minimal = {
      schema_version: 3,
      report_id: "r-empty",
      generated_at: "2026-05-09T00:00:00Z",
    };
    const result = ReportV3Schema.safeParse(minimal);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.personas).toEqual([]);
      expect(result.data.claims).toEqual([]);
      expect(result.data.data_gaps).toEqual([]);
    }
  });
});
