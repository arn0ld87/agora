/**
 * Streitfrage-Contract-Spec (Issue #1778, Schritt 1.4).
 *
 * Zwei Validator-Fälle aus dem Backend-Contract plus Schema-Drift-Check
 * gegen die generierte schemas/contested-question.schema.json.
 */
import { describe, it, expect } from 'vitest';
import { ContestedQuestionSchema } from '../contestedQuestionContract';
import contestedQuestionJson from '../../../../schemas/contested-question.schema.json';

const STATEMENT =
  'Die Geburtshilfe in Brenkhausen wird zum 30. Juni 2027 geschlossen.';

function propertyKeys(schema: { properties?: Record<string, unknown> }) {
  return Object.keys(schema.properties ?? {}).sort();
}

function shapeKeys(schema: { shape: Record<string, unknown> }) {
  return Object.keys(schema.shape).sort();
}

describe('contestedQuestionContract — Validierung', () => {
  it('akzeptiert eine Aussage mit origin "assistant"', () => {
    const result = ContestedQuestionSchema.parse({
      statement: STATEMENT,
      origin: 'assistant',
      absence_reason: null,
    });
    expect(result.origin).toBe('assistant');
    expect(result.statement).toBe(STATEMENT);
  });

  it('lehnt origin "none" mit Aussage ab', () => {
    expect(() =>
      ContestedQuestionSchema.parse({
        statement: STATEMENT,
        origin: 'none',
        absence_reason: null,
      }),
    ).toThrow();
  });
});

describe('contestedQuestionContract — Schema-Drift', () => {
  it('matcht contested-question.schema.json', () => {
    expect(shapeKeys(ContestedQuestionSchema)).toEqual(
      propertyKeys(contestedQuestionJson),
    );
  });
});
