/**
 * Antwort-Envelopes der Berichts-Artefakte (Issue #1804, Etappe 5).
 *
 * Validierungsfälle plus Schema-Drift-Check gegen die generierten
 * schemas/evidence-density-response.schema.json und
 * schemas/stance-analysis-response.schema.json.
 */
import { describe, it, expect } from 'vitest';
import {
  EvidenceDensityResponseOmittedSchema,
  EvidenceDensityResponseSchema,
  EvidenceDensityResponseSuccessSchema,
  ReportArtifactOmissionSchema,
  StanceAnalysisResponseOmittedSchema,
  StanceAnalysisResponseSchema,
  StanceAnalysisResponseSuccessSchema,
} from '../reportArtifactContract';
import densityResponseJson from '../../../../schemas/evidence-density-response.schema.json';
import stanceResponseJson from '../../../../schemas/stance-analysis-response.schema.json';

type JsonSchema = {
  $defs: Record<string, { properties?: Record<string, unknown>; required?: string[] }>;
};

function keys(schema: { properties?: Record<string, unknown> }) {
  return Object.keys(schema.properties ?? {}).sort();
}

const omission = {
  artifact: 'evidence_density',
  reason: 'contract_violation',
  detail: 'Datei verletzt den Vertrag.',
  validation_errors: ['claims_total: Value error'],
};

describe('evidence-density response — Validierung', () => {
  it('akzeptiert die Erfolgsvariante', () => {
    const parsed = EvidenceDensityResponseSchema.parse({
      success: true,
      data: { claims_total: 0 },
    });
    expect('data' in parsed && parsed.data.claims_total).toBe(0);
  });

  it('akzeptiert die Omission-Variante und setzt validation_errors auf []', () => {
    const parsed = EvidenceDensityResponseSchema.parse({
      success: true,
      artifact_omitted: { artifact: 'evidence_density', reason: 'contract_violation', detail: 'x' },
    });
    expect('artifact_omitted' in parsed && parsed.artifact_omitted.validation_errors).toEqual([]);
  });

  it('lehnt weder-noch und beides zugleich ab', () => {
    expect(() => EvidenceDensityResponseSchema.parse({ success: true })).toThrow();
    expect(() =>
      EvidenceDensityResponseSchema.parse({ success: true, data: {}, artifact_omitted: omission }),
    ).toThrow();
  });

  it('lehnt eine Antwort ohne success ab', () => {
    expect(() => EvidenceDensityResponseSchema.parse({ data: {} })).toThrow();
  });

  it('lehnt vertragswidrige Daten in der Erfolgsvariante ab', () => {
    expect(() =>
      EvidenceDensityResponseSchema.parse({ success: true, data: { claims_total: 3 } }),
    ).toThrow();
  });
});

describe('stance-analysis response — Validierung', () => {
  it('akzeptiert eine nicht anwendbare Analyse als Daten', () => {
    const parsed = StanceAnalysisResponseSchema.parse({
      success: true,
      data: { applicable: false },
    });
    expect('data' in parsed && parsed.data.applicable).toBe(false);
  });

  it('akzeptiert die Omission-Variante', () => {
    const parsed = StanceAnalysisResponseSchema.parse({
      success: true,
      artifact_omitted: { ...omission, artifact: 'stance_analysis' },
    });
    expect('artifact_omitted' in parsed && parsed.artifact_omitted.artifact).toBe('stance_analysis');
  });

  it('lehnt eine Quote über 1 in der Erfolgsvariante ab', () => {
    expect(() =>
      StanceAnalysisResponseSchema.parse({
        success: true,
        data: { applicable: true, positioning_ratio: 2 },
      }),
    ).toThrow();
  });

  it('lehnt mehr als fünf Validierungsfehler ab', () => {
    expect(() =>
      ReportArtifactOmissionSchema.parse({ ...omission, validation_errors: ['1', '2', '3', '4', '5', '6'] }),
    ).toThrow();
  });
});

describe('reportArtifactContract — Schema-Drift', () => {
  const density = densityResponseJson as unknown as JsonSchema;
  const stance = stanceResponseJson as unknown as JsonSchema;

  it('Omission-Modell stimmt mit beiden generierten Schemas überein', () => {
    for (const json of [density, stance]) {
      const def = json.$defs.ReportArtifactOmissionModel;
      expect(Object.keys(ReportArtifactOmissionSchema.shape).sort()).toEqual(keys(def));
      expect([...(def.required ?? [])].sort()).toEqual(['artifact', 'detail', 'reason']);
    }
  });

  it('Varianten der Belegdichte-Antwort matchen das Schema', () => {
    expect(Object.keys(EvidenceDensityResponseSuccessSchema.shape).sort()).toEqual(
      keys(density.$defs.EvidenceDensityResponseSuccessVariant),
    );
    expect(Object.keys(EvidenceDensityResponseOmittedSchema.shape).sort()).toEqual(
      keys(density.$defs.EvidenceDensityResponseOmittedVariant),
    );
  });

  it('Varianten der Haltungs-Antwort matchen das Schema', () => {
    expect(Object.keys(StanceAnalysisResponseSuccessSchema.shape).sort()).toEqual(
      keys(stance.$defs.StanceAnalysisResponseSuccessVariant),
    );
    expect(Object.keys(StanceAnalysisResponseOmittedSchema.shape).sort()).toEqual(
      keys(stance.$defs.StanceAnalysisResponseOmittedVariant),
    );
  });

  it('success ist in jeder Variante Pflicht', () => {
    for (const [json, names] of [
      [density, ['EvidenceDensityResponseSuccessVariant', 'EvidenceDensityResponseOmittedVariant']],
      [stance, ['StanceAnalysisResponseSuccessVariant', 'StanceAnalysisResponseOmittedVariant']],
    ] as const) {
      for (const name of names) expect(json.$defs[name].required).toContain('success');
    }
  });
});
