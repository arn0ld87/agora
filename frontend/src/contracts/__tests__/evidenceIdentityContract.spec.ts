import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import * as reportContract from '../reportContract';
import { ReportV3Schema } from '../reportV3Contract';

function exportedSchema(moduleValue: object, exportName: string): z.ZodType {
  const candidate: unknown = Reflect.get(moduleValue, exportName);
  if (!(candidate instanceof z.ZodType)) {
    throw new Error(`reportContract muss ${exportName} exportieren`);
  }
  return candidate;
}

const EVIDENCE_ID = 'ev_47f9a1c2d4e5689a01bc23de45fa678b';
const UNKNOWN_EVIDENCE_ID = 'ev_00000000000000000000000000000000';
const MISMATCHED_EVIDENCE_ID = 'ev_ffffffffffffffffffffffffffffffff';

const EVIDENCE_RECORD = {
  evidence_id: EVIDENCE_ID,
  producer_key: 'agent-log:42#post:1234',
  type: 'agent_interview',
  source: 'agent_log',
  snippet: 'Persona kmu_ceo äußerte konkrete Sicherheitsbedenken.',
  quote: 'Die Freigabe ohne Sicherheitsprüfung kommt für uns nicht infrage.',
  source_id_anchor: 'agent-log-42#post-1234',
  source_kind: 'agent_quote',
  persona_stakeholder_group: 'Geschaeftsfuehrung',
};

const CLAIM_EVIDENCE_BINDING = {
  evidence_id: EVIDENCE_ID,
  match_score: 0.91,
  retrieval_score: 0.91,
  entailment: 'SUPPORTED',
  entailment_reason: 'Das Originalzitat stützt die Aussage direkt.',
  supports_claim: true,
  contradicts_claim: false,
};

const EVIDENCE_INDEX = {
  [EVIDENCE_ID]: EVIDENCE_RECORD,
};

const EVIDENCE_MAP_V3 = {
  schema_version: 3,
  report_id: 'report_abc',
  simulation_id: 'sim_abc',
  evidence_index: EVIDENCE_INDEX,
  global_evidence_refs: [EVIDENCE_ID],
  sections: [
    {
      section_index: 1,
      section_title: 'Erster Eindruck',
      section_summary: 'Die Zielgruppe verlangt belastbare Sicherheitsnachweise.',
      claims: [
        {
          claim_id: 'claim_01',
          claim_text: 'Sicherheitsbedenken prägen die erste Reaktion.',
          confidence_label: 'low',
          confidence_score: 0.42,
          evidence: [CLAIM_EVIDENCE_BINDING],
          audit_trail: [],
        },
      ],
    },
  ],
};

const REPORT_V4 = {
  schema_version: 4,
  report_id: 'report_abc',
  generated_at: '2026-08-09T12:00:00Z',
  evidence_index: EVIDENCE_INDEX,
  claims: [
    {
      id: 'claim_01',
      statement: 'Sicherheitsbedenken prägen die erste Reaktion.',
      evidence_refs: [EVIDENCE_ID],
      confidence: 'low',
      persona_ids: [],
      aggregation_basis: 'persona',
    },
  ],
};

describe('kanonische Evidence-Identität', () => {
  it('trennt verpflichtende Quellenidentität von claim-relativen Binding-Werten', () => {
    const EvidenceRecordSchema = exportedSchema(reportContract, 'EvidenceRecordSchema');

    expect(EvidenceRecordSchema.safeParse(EVIDENCE_RECORD).success).toBe(true);
    expect(
      EvidenceRecordSchema.safeParse({
        ...EVIDENCE_RECORD,
        evidence_id: undefined,
      }).success,
    ).toBe(false);
    expect(
      EvidenceRecordSchema.safeParse({
        ...EVIDENCE_RECORD,
        producer_key: undefined,
      }).success,
    ).toBe(false);
    expect(
      EvidenceRecordSchema.safeParse({
        ...EVIDENCE_RECORD,
        evidence_id: 'ev_47f9a1c2',
      }).success,
    ).toBe(false);
    expect(
      EvidenceRecordSchema.safeParse({
        ...EVIDENCE_RECORD,
        retrieval_score: 0.91,
        entailment: 'SUPPORTED',
        supports_claim: true,
      }).success,
    ).toBe(false);
  });

  it('modelliert Evidence-Bindings ausschließlich mit evidence_id und claim-relativen Werten', () => {
    const ClaimEvidenceBindingSchema = exportedSchema(
      reportContract,
      'ClaimEvidenceBindingSchema',
    );

    const result = ClaimEvidenceBindingSchema.safeParse(CLAIM_EVIDENCE_BINDING);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data).toMatchObject({
        evidence_id: EVIDENCE_ID,
        match_score: 0.91,
        retrieval_score: 0.91,
        entailment: 'SUPPORTED',
        supports_claim: true,
        contradicts_claim: false,
      });
    }
    expect(
      ClaimEvidenceBindingSchema.safeParse({
        ...CLAIM_EVIDENCE_BINDING,
        evidence_id: undefined,
      }).success,
    ).toBe(false);
    expect(
      ClaimEvidenceBindingSchema.safeParse({
        ...CLAIM_EVIDENCE_BINDING,
        evidence_id: 'ev_47F9A1C2D4E5689A01BC23DE45FA678B',
      }).success,
    ).toBe(false);
    expect(
      ClaimEvidenceBindingSchema.safeParse({
        ...CLAIM_EVIDENCE_BINDING,
        source: 'agent_log',
        snippet: 'Quellenfelder gehören in den EvidenceRecord.',
        quote: 'Kein Binding-Feld.',
        persona_stakeholder_group: 'Geschaeftsfuehrung',
      }).success,
    ).toBe(false);
  });

  it('parst EvidenceMap v3 nur mit auflösbaren Referenzen und konsistentem Indexschlüssel', () => {
    const valid = reportContract.EvidenceMapSchema.safeParse(EVIDENCE_MAP_V3);
    expect(valid.success).toBe(true);

    const unknownGlobalRef = {
      ...EVIDENCE_MAP_V3,
      global_evidence_refs: [UNKNOWN_EVIDENCE_ID],
    };
    expect(reportContract.EvidenceMapSchema.safeParse(unknownGlobalRef).success).toBe(false);

    const mismatchedIndexKey = {
      ...EVIDENCE_MAP_V3,
      evidence_index: {
        [MISMATCHED_EVIDENCE_ID]: EVIDENCE_RECORD,
      },
    };
    expect(reportContract.EvidenceMapSchema.safeParse(mismatchedIndexKey).success).toBe(false);
  });

  it('defaultet gate_decision_log auf [] und übernimmt Einträge unverändert (PR #1151)', () => {
    // Persistierte Maps von vor PR #1151 tragen das Feld nicht.
    const withoutLog = reportContract.EvidenceMapSchema.safeParse(EVIDENCE_MAP_V3);
    expect(withoutLog.success).toBe(true);
    if (withoutLog.success) {
      expect(withoutLog.data.gate_decision_log).toEqual([]);
    }

    const gateDecision = {
      section_index: 2,
      claim_id: 'claim_01',
      violation: 'no_supporting_evidence',
      action: 'moved_to_hypotheses',
      detail: 'Keine direkte Evidence gebunden.',
    };
    const withLog = reportContract.EvidenceMapSchema.safeParse({
      ...EVIDENCE_MAP_V3,
      gate_decision_log: [gateDecision],
    });
    expect(withLog.success).toBe(true);
    if (withLog.success) {
      expect(withLog.data.gate_decision_log).toEqual([gateDecision]);
    }
  });

  it('lehnt EvidenceMap schema_version 2 nach dem echten Versionssprung ab', () => {
    const legacyVersion = {
      ...EVIDENCE_MAP_V3,
      schema_version: 2,
    };
    expect(reportContract.EvidenceMapSchema.safeParse(legacyVersion).success).toBe(false);
  });

  it('lehnt high-Claims mit beliebiger gebundener inferred-Evidence ab', () => {
    const secondQuoteId = 'ev_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
    const inferredId = 'ev_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
    const highClaimWithNonSupportingInference = {
      ...EVIDENCE_MAP_V3,
      evidence_index: {
        ...EVIDENCE_INDEX,
        [secondQuoteId]: {
          ...EVIDENCE_RECORD,
          evidence_id: secondQuoteId,
          producer_key: 'agent-log:43#post:5678',
          persona_stakeholder_group: 'IT-Abteilung',
        },
        [inferredId]: {
          evidence_id: inferredId,
          producer_key: 'audit-trail:inference-1',
          type: 'entity_summary',
          source: 'report_tool',
          snippet: 'Abgeleitete Interpretation ohne verifizierbare Quelle.',
          source_kind: 'inferred',
        },
      },
      sections: [
        {
          ...EVIDENCE_MAP_V3.sections[0],
          claims: [
            {
              ...EVIDENCE_MAP_V3.sections[0].claims[0],
              confidence_label: 'high',
              confidence_score: 0.82,
              evidence: [
                CLAIM_EVIDENCE_BINDING,
                {
                  ...CLAIM_EVIDENCE_BINDING,
                  evidence_id: secondQuoteId,
                },
                {
                  evidence_id: inferredId,
                  match_score: 0.4,
                  retrieval_score: 0.4,
                  entailment: 'RELATED_ONLY',
                  supports_claim: false,
                  contradicts_claim: false,
                },
              ],
            },
          ],
        },
      ],
    };

    const result = reportContract.EvidenceMapSchema.safeParse(highClaimWithNonSupportingInference);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            path: ['sections', 0, 'claims', 0, 'evidence'],
            message: expect.stringContaining('source_kind=inferred'),
          }),
        ]),
      );
    }
  });

  it('parst ReportV3 nur als Version 4 mit eingebettetem, auflösbarem evidence_index', () => {
    const valid = ReportV3Schema.safeParse(REPORT_V4);
    expect(valid.success).toBe(true);

    const unknownClaimRef = {
      ...REPORT_V4,
      claims: [
        {
          ...REPORT_V4.claims[0],
          evidence_refs: [UNKNOWN_EVIDENCE_ID],
        },
      ],
    };
    expect(ReportV3Schema.safeParse(unknownClaimRef).success).toBe(false);

    const mismatchedIndexKey = {
      ...REPORT_V4,
      evidence_index: {
        [MISMATCHED_EVIDENCE_ID]: EVIDENCE_RECORD,
      },
    };
    expect(ReportV3Schema.safeParse(mismatchedIndexKey).success).toBe(false);
  });

  it('lehnt ReportV3 schema_version 3 nach dem echten Versionssprung ab', () => {
    const legacyVersion = {
      schema_version: 3,
      report_id: 'report_abc',
      generated_at: '2026-08-09T12:00:00Z',
    };
    expect(ReportV3Schema.safeParse(legacyVersion).success).toBe(false);
  });
});
