/**
 * Zod-Spiegel-Drift-Test gegen den Backend-Vertrag.
 *
 * Sample-Payload ist 1:1 aus backend/tests/contracts/test_report_contract.py
 * (`test_full_contract_round_trip`). Wenn Backend-Pydantic-Modelle wandern,
 * muss dieser Test brechen, bis der Zod-Spiegel nachgezogen ist.
 */
import { describe, it, expect } from 'vitest';
import {
  parseReportContract,
  ReportContractSchema,
  ReportClaimSchema,
  EvidenceItemSchema,
} from '../reportContract';

const VALID_PAYLOAD = {
  schema_version: 2,
  exported_at: '2026-05-02T10:00:00Z',
  report: {
    schema_version: 2,
    report_id: 'report_abc',
    simulation_id: 'sim_abc',
    graph_id: 'graph_abc',
    simulation_requirement: 'Wahrnehmung simulieren',
    status: 'completed',
    markdown_content: '# Bericht',
    has_evidence: true,
    evidence_sections: 1,
  },
  evidence: {
    schema_version: 2,
    report_id: 'report_abc',
    simulation_id: 'sim_abc',
    global_evidence: [],
    sections: [
      {
        section_index: 1,
        section_title: 'Erster Eindruck',
        section_summary: 'Zusammenfassung',
        claims: [
          {
            claim_id: 'claim_01',
            claim_text: 'Die Personas reagieren skeptisch.',
            confidence_label: 'high',
            confidence_score: 0.78,
            evidence: [
              {
                type: 'agent_action',
                source: 'agent_log',
                snippet: 'Persona kmu_ceo äußerte Bedenken.',
                match_score: 0.7,
                supports_claim: true,
              },
            ],
            audit_trail: [],
          },
        ],
      },
    ],
  },
};

describe('ReportContractSchema (Zod-Spiegel)', () => {
  it('parses the canonical Backend round-trip payload', () => {
    const result = parseReportContract(VALID_PAYLOAD);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.schema_version).toBe(2);
      expect(result.data.evidence?.sections[0].claims[0].claim_id).toBe('claim_01');
    }
  });

  it('rejects schema_version=1 (Literal[2] enforced)', () => {
    const bad = { ...VALID_PAYLOAD, schema_version: 1 };
    expect(ReportContractSchema.safeParse(bad).success).toBe(false);
  });

  it('rejects evidence-map on schema_version=1', () => {
    const bad = {
      ...VALID_PAYLOAD,
      evidence: { ...VALID_PAYLOAD.evidence, schema_version: 1 },
    };
    expect(ReportContractSchema.safeParse(bad).success).toBe(false);
  });

  it('rejects claim_id that does not match the Pydantic regex', () => {
    const bad = {
      claim_id: 'c1',
      claim_text: 'Lange genug für min(8)',
      confidence_label: 'low',
      confidence_score: 0.1,
      evidence: [],
      audit_trail: [],
    };
    expect(ReportClaimSchema.safeParse(bad).success).toBe(false);
  });

  it('rejects model_generated_inference inside evidence (audit_trail-only)', () => {
    const bad = {
      type: 'model_generated_inference',
      source: 'x',
      snippet: 'x',
    };
    expect(EvidenceItemSchema.safeParse(bad).success).toBe(false);
  });

  it('rejects "verified" without match_score >= 0.85', () => {
    const bad = {
      claim_id: 'claim_42',
      claim_text: 'Lange genug für min(8)',
      confidence_label: 'verified',
      confidence_score: 0.9,
      evidence: [
        {
          type: 'graph_metric',
          source: 'x',
          snippet: 'snippet',
          match_score: 0.4,
          supports_claim: true,
        },
      ],
      audit_trail: [],
    };
    expect(ReportClaimSchema.safeParse(bad).success).toBe(false);
  });

  it('rejects "high" without supports_claim=true (Anti-Dekoration)', () => {
    const bad = {
      claim_id: 'claim_43',
      claim_text: 'Lange genug für min(8)',
      confidence_label: 'high',
      confidence_score: 0.7,
      evidence: [
        {
          type: 'graph_metric',
          source: 'x',
          snippet: 'snippet',
          match_score: 0.6,
          supports_claim: false,
        },
      ],
      audit_trail: [],
    };
    expect(ReportClaimSchema.safeParse(bad).success).toBe(false);
  });
});
