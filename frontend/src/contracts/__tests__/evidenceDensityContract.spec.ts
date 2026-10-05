/**
 * Belegdichte-Contract-Spec (Issue #1779, Schritt 2.1).
 *
 * Validierungsfälle aus dem Backend-Contract plus Schema-Drift-Check gegen
 * die generierte schemas/evidence-density.schema.json.
 */
import { describe, it, expect } from 'vitest';
import { EvidenceDensitySchema } from '../evidenceDensityContract';
import evidenceDensityJson from '../../../../schemas/evidence-density.schema.json';

function propertyKeys(schema: { properties?: Record<string, unknown> }) {
  return Object.keys(schema.properties ?? {}).sort();
}

describe('evidenceDensityContract — Validierung', () => {
  it('akzeptiert eine Zählung mit Claims', () => {
    const result = EvidenceDensitySchema.parse({
      claims_total: 4,
      claims_without_support: 1,
      claims_single_support: 2,
      claims_multi_support: 1,
      claims_multi_independent: 1,
      claims_at_single_source_cap: 2,
      claims_with_action_support: 1,
      supporting_links_by_type: { agent_interview: 3, agent_action: 1 },
      single_support_ratio: 0.5,
      action_support_ratio: 0.25,
      single_source_cap_ratio: 0.5,
      multi_independent_ratio: 0.25,
    });
    expect(result.claims_total).toBe(4);
    expect(result.schema_version).toBe(1);
  });

  it('akzeptiert eine leere Zählung ohne Quoten', () => {
    const result = EvidenceDensitySchema.parse({});
    expect(result.claims_total).toBe(0);
    expect(result.single_support_ratio).toBeUndefined();
  });

  it('lehnt inkonsistente Summen ab', () => {
    expect(() =>
      EvidenceDensitySchema.parse({ claims_total: 3, claims_single_support: 1 }),
    ).toThrow();
  });

  it('lehnt eine Quote über 1 ab', () => {
    expect(() =>
      EvidenceDensitySchema.parse({ single_support_ratio: 1.2 }),
    ).toThrow();
  });

  it('lehnt unbekannte Felder ab', () => {
    expect(() => EvidenceDensitySchema.parse({ extra: true })).toThrow();
  });
});

describe('evidenceDensityContract — Schema-Drift', () => {
  it('matcht evidence-density.schema.json', () => {
    expect(Object.keys(EvidenceDensitySchema.shape).sort()).toEqual(
      propertyKeys(evidenceDensityJson),
    );
  });
});
