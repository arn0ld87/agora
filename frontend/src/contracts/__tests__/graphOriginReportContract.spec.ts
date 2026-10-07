import { describe, expect, it } from 'vitest';
import { EvidenceItemSchema, EvidenceRecordSchema } from '../reportContract';

const graphEvidence = {
  type: 'graph_fact',
  source: 'graph',
  snippet: 'Von Hand bearbeitete Beziehung.',
  source_kind: 'graph_relation',
};
const record = {
  ...graphEvidence,
  evidence_id: 'ev_00000000000000000000000000000001',
  producer_key: 'graph:relation:1',
};

describe('graph_origin im Report-Vertrag (ADR-0022)', () => {
  it.each(['manual', 'edited', null])('erhaelt die Herkunft %s in Item und Record', (origin) => {
    expect(EvidenceItemSchema.parse({ ...graphEvidence, graph_origin: origin }).graph_origin).toBe(origin);
    expect(EvidenceRecordSchema.parse({ ...record, graph_origin: origin }).graph_origin).toBe(origin);
  });

  it('akzeptiert Altbestand ohne Herkunftsfeld', () => {
    expect(EvidenceItemSchema.safeParse(graphEvidence).success).toBe(true);
    expect(EvidenceRecordSchema.safeParse(record).success).toBe(true);
  });

  it.each(['manual', 'edited'])('verbietet fuer %s Dokumentfakten und seed_doc-Anker', (origin) => {
    for (const base of [graphEvidence, record]) {
      const schema = 'evidence_id' in base ? EvidenceRecordSchema : EvidenceItemSchema;
      expect(schema.safeParse({ ...base, graph_origin: origin, source_kind: 'seed_corpus' }).success).toBe(false);
      expect(schema.safeParse({ ...base, graph_origin: origin, source_id_anchor: 'seed_doc:doc1:chunk1' }).success).toBe(false);
      expect(schema.safeParse({ ...base, graph_origin: origin, source_id_anchor: 'graph:relation:1' }).success).toBe(true);
    }
  });

  it('weist unbekannte Herkunftswerte ab', () => {
    expect(EvidenceItemSchema.safeParse({ ...graphEvidence, graph_origin: 'generated' }).success).toBe(false);
    expect(EvidenceRecordSchema.safeParse({ ...record, graph_origin: 'generated' }).success).toBe(false);
  });
});
