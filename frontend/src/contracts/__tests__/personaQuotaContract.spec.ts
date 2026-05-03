/**
 * Sub-Slice 20c — Zod-Spiegel-Tests für PersonaQuotaPlan.
 *
 * Backend-Quelle: backend/app/contracts/persona_contract.py
 * Schema: schemas/persona-quota-plan.schema.json
 */
import { describe, it, expect } from "vitest";
import {
  PersonaQuotaPlanSchema,
  buildQuotaPlanFromEntries,
} from "../personaQuotaContract";

describe("PersonaQuotaPlanSchema", () => {
  it("akzeptiert konsistenten Plan", () => {
    const result = PersonaQuotaPlanSchema.safeParse({
      targets: { kmu_ceo: 8, it_admin: 6 },
      total: 14,
    });
    expect(result.success).toBe(true);
  });

  it("lehnt Plan mit total != sum(targets) ab", () => {
    const result = PersonaQuotaPlanSchema.safeParse({
      targets: { kmu_ceo: 8, it_admin: 6 },
      total: 99,
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      const messages = result.error.issues.map((i) => i.message).join(" ");
      expect(messages).toMatch(/inkonsistent|sum/i);
    }
  });

  it("lehnt leeren Plan ab", () => {
    const result = PersonaQuotaPlanSchema.safeParse({ targets: {}, total: 1 });
    expect(result.success).toBe(false);
  });

  it("lehnt count < 1 ab", () => {
    const result = PersonaQuotaPlanSchema.safeParse({
      targets: { kmu_ceo: 0 },
      total: 0,
    });
    expect(result.success).toBe(false);
  });

  it("lehnt count > 200 ab (Backend-Constraint min/max)", () => {
    const result = PersonaQuotaPlanSchema.safeParse({
      targets: { kmu_ceo: 999 },
      total: 999,
    });
    expect(result.success).toBe(false);
  });

  it("lehnt total > 500 ab", () => {
    const result = PersonaQuotaPlanSchema.safeParse({
      targets: { a: 200, b: 200, c: 200 },
      total: 600,
    });
    expect(result.success).toBe(false);
  });

  it("lehnt zusätzliche Felder ab (extra=forbid)", () => {
    const result = PersonaQuotaPlanSchema.safeParse({
      targets: { kmu_ceo: 1 },
      total: 1,
      extra: "should-fail",
    });
    expect(result.success).toBe(false);
  });
});

describe("buildQuotaPlanFromEntries", () => {
  it("baut targets-dict + total aus UI-Entries", () => {
    const plan = buildQuotaPlanFromEntries([
      { segment: "kmu_ceo", count: 8 },
      { segment: "it_admin", count: 6 },
    ]);
    expect(plan.targets).toEqual({ kmu_ceo: 8, it_admin: 6 });
    expect(plan.total).toBe(14);
  });

  it("droppt leere Segment-Strings", () => {
    const plan = buildQuotaPlanFromEntries([
      { segment: "kmu_ceo", count: 5 },
      { segment: "", count: 99 },
    ]);
    expect(plan.targets).toEqual({ kmu_ceo: 5 });
    expect(plan.total).toBe(5);
  });

  it("ergibt einen Plan, den der Schema-Validator akzeptiert", () => {
    const plan = buildQuotaPlanFromEntries([
      { segment: "kmu_ceo", count: 8 },
      { segment: "it_admin", count: 6 },
    ]);
    const result = PersonaQuotaPlanSchema.safeParse(plan);
    expect(result.success).toBe(true);
  });
});
