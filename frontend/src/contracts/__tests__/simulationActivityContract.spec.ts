/**
 * Aktivitätsmodell-Contract-Spec (Issue #1779, Schritt 2.4).
 *
 * Validierungsfälle aus dem Backend-Contract plus Schema-Drift-Check gegen
 * die generierte schemas/simulation-activity-model.schema.json.
 */
import { describe, it, expect } from 'vitest';
import {
  ActivityModeSchema,
  ActivityModelConfigSchema,
  ActorClassSchema,
} from '../simulationActivityContract';
import activityModelJson from '../../../../schemas/simulation-activity-model.schema.json';

function propertyKeys(schema: { properties?: Record<string, unknown> }) {
  return Object.keys(schema.properties ?? {}).sort();
}

function validModel() {
  return {
    mode: 'realistic',
    max_text_actions_per_activation: 1,
    max_reactions_per_activation: 2,
    text_posts_per_day: {
      individual: 0.5,
      politician: 1,
      authority: 0.5,
      organisation: 1,
      media: 3,
    },
    hourly_weights: Array.from({ length: 24 }, () => 1 / 24),
  };
}

describe('simulationActivityContract — Validierung', () => {
  it('akzeptiert beide Modi und lehnt andere ab', () => {
    expect(ActivityModeSchema.parse('realistic')).toBe('realistic');
    expect(ActivityModeSchema.parse('active')).toBe('active');
    expect(() => ActivityModeSchema.parse('turbo')).toThrow();
  });

  it('akzeptiert ein vollständiges Aktivitätsmodell', () => {
    const result = ActivityModelConfigSchema.parse(validModel());
    expect(result.mode).toBe('realistic');
    expect(result.schema_version).toBe(1);
  });

  it('lehnt eine fehlende Akteursklasse ab', () => {
    const model = validModel();
    delete (model.text_posts_per_day as Record<string, number>).media;
    expect(() => ActivityModelConfigSchema.parse(model)).toThrow();
  });

  it('lehnt negative Tagesraten ab', () => {
    const model = validModel();
    model.text_posts_per_day.media = -1;
    expect(() => ActivityModelConfigSchema.parse(model)).toThrow();
  });

  it('lehnt ein Stundenprofil mit falscher Länge oder Summe ab', () => {
    expect(() =>
      ActivityModelConfigSchema.parse({ ...validModel(), hourly_weights: [1] }),
    ).toThrow();
    expect(() =>
      ActivityModelConfigSchema.parse({
        ...validModel(),
        hourly_weights: Array.from({ length: 24 }, () => 0.1),
      }),
    ).toThrow();
  });

  it('lehnt unbekannte Felder und Obergrenze 0 für Textaktionen ab', () => {
    expect(() =>
      ActivityModelConfigSchema.parse({ ...validModel(), extra: true }),
    ).toThrow();
    expect(() =>
      ActivityModelConfigSchema.parse({
        ...validModel(),
        max_text_actions_per_activation: 0,
      }),
    ).toThrow();
  });
});

describe('simulationActivityContract — Schema-Drift', () => {
  it('matcht simulation-activity-model.schema.json (Felder)', () => {
    expect(Object.keys(ActivityModelConfigSchema.shape).sort()).toEqual(
      propertyKeys(activityModelJson),
    );
  });

  it('matcht die Enum-Werte von ActivityMode und ActorClass', () => {
    const defs = activityModelJson.$defs;
    expect([...ActivityModeSchema.options]).toEqual(defs.ActivityMode.enum);
    expect([...ActorClassSchema.options]).toEqual(defs.ActorClass.enum);
  });
});
