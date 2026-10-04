/**
 * Haltungsanalyse-Contract-Spec (Issue #1778, Schritt 1.8).
 *
 * Validierungsfälle aus dem Backend-Contract plus Schema-Drift-Check gegen
 * die generierte schemas/stance-analysis.schema.json.
 */
import { describe, it, expect } from 'vitest';
import {
  ClassifiedContributionSchema,
  StanceAnalysisSchema,
  StanceClassSchema,
  VoiceStanceSchema,
} from '../stanceAnalysisContract';
import stanceAnalysisJson from '../../../../schemas/stance-analysis.schema.json';

const STATEMENT =
  'Die Geburtshilfe in Brenkhausen wird zum 30. Juni 2027 geschlossen.';

function propertyKeys(schema: { properties?: Record<string, unknown> }) {
  return Object.keys(schema.properties ?? {}).sort();
}

function shapeKeys(schema: { shape: Record<string, unknown> }) {
  return Object.keys(schema.shape).sort();
}

describe('stanceAnalysisContract — Validierung', () => {
  it('akzeptiert eine Analyse mit Stimmen und Beiträgen', () => {
    const result = StanceAnalysisSchema.parse({
      contested_statement: STATEMENT,
      applicable: true,
      voices_total: 2,
      voices_positioned: 1,
      positioning_ratio: 0.5,
      camp_distribution: { in_favour: 0, opposed: 1, undecided: 1 },
      voices: [
        {
          voice_key: 'agent:0',
          agent_name: 'Hebamme Lena',
          role_family: null,
          start_class: 'opposed',
          contribution_classes: ['opposed'],
          interview_class: null,
        },
        {
          voice_key: 'agent:1',
          agent_name: 'Klinikleitung',
          role_family: null,
          start_class: 'in_favour',
          contribution_classes: [],
          interview_class: null,
        },
      ],
      contributions: [
        {
          agent_id: 0,
          agent_name: 'Hebamme Lena',
          platform: 'reddit',
          round_num: 1,
          action_type: 'CREATE_POST',
          producer_key:
            'simulation-action:reddit:1:0:CREATE_POST:2026-01-01T01:00:00',
          stance_class: 'opposed',
        },
      ],
      classified_total: 1,
      classification_failed: 0,
    });

    expect(result.positioning_ratio).toBe(0.5);
    expect(result.camp_distribution.opposed).toBe(1);
    expect(result.voices).toHaveLength(2);
  });

  it('akzeptiert die nicht anwendbare Analyse eines Laufs ohne Streitfrage', () => {
    const result = StanceAnalysisSchema.parse({
      contested_statement: null,
      applicable: false,
      voices_total: 0,
      voices_positioned: 0,
      positioning_ratio: null,
      camp_distribution: {},
      voices: [],
      contributions: [],
      classified_total: 0,
      classification_failed: 0,
    });

    expect(result.applicable).toBe(false);
    expect(result.camp_distribution).toEqual({});
  });

  it('lehnt eine unbekannte Haltung ab', () => {
    expect(() => StanceClassSchema.parse('neutral')).toThrow();
  });

  it('lehnt eine Positionierungsquote über 1 ab', () => {
    expect(() =>
      StanceAnalysisSchema.parse({ applicable: true, positioning_ratio: 1.2 }),
    ).toThrow();
  });

  it('lehnt unbekannte Felder ab', () => {
    expect(() =>
      StanceAnalysisSchema.parse({ applicable: false, extra: true }),
    ).toThrow();
  });
});

describe('stanceAnalysisContract — Schema-Drift', () => {
  it('matcht stance-analysis.schema.json', () => {
    expect(shapeKeys(StanceAnalysisSchema)).toEqual(
      propertyKeys(stanceAnalysisJson),
    );
  });

  it('matcht die Unterschemata VoiceStance und ClassifiedContribution', () => {
    expect(shapeKeys(VoiceStanceSchema)).toEqual(
      propertyKeys(stanceAnalysisJson.$defs.VoiceStance),
    );
    expect(shapeKeys(ClassifiedContributionSchema)).toEqual(
      propertyKeys(stanceAnalysisJson.$defs.ClassifiedContribution),
    );
  });

  it('kennt genau die Haltungen des Backend-Vertrags', () => {
    expect(StanceClassSchema.options).toEqual(
      stanceAnalysisJson.$defs.VoiceStance.properties.start_class.enum,
    );
  });
});
