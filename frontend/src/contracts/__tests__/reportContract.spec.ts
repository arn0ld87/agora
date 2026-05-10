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
  ReportOutlineSchema,
  ReportSectionHypothesisSchema,
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
        hypotheses: [
          {
            hypothesis_id: 'hypothesis_01',
            hypothesis_text: 'Indizien legen eine zweite Zielgruppe nahe.',
            rationale: 'Es gibt Signale im Abschnitt, aber noch keine direkte Evidence.',
            suggested_evidence: ['weitere Persona-Quote'],
          },
        ],
        claims: [
          {
            claim_id: 'claim_01',
            claim_text: 'Die Personas reagieren skeptisch.',
            confidence_label: 'high',
            confidence_score: 0.78,
            // ADR-0002 Anker 4 (Sub-Slice M11.7b): high verlangt agent_quote-
            // Evidence aus mindestens 2 Stakeholder-Gruppen.
            evidence: [
              {
                type: 'agent_interview',
                source: 'agent_log',
                snippet: 'Persona kmu_ceo äußerte Bedenken.',
                match_score: 0.7,
                supports_claim: true,
                source_kind: 'agent_quote',
                persona_stakeholder_group: 'Geschaeftsfuehrung',
              },
              {
                type: 'agent_interview',
                source: 'agent_log',
                snippet: 'Persona it_lead bestaetigte das Problem.',
                match_score: 0.72,
                supports_claim: true,
                source_kind: 'agent_quote',
                persona_stakeholder_group: 'IT-Abteilung',
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
      expect(result.data.evidence?.sections[0].hypotheses[0].hypothesis_id).toBe('hypothesis_01');
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

  it('parses sample with quote+anchor (Task 12)', () => {
    const item = {
      type: 'agent_action',
      source: 'agent_log',
      snippet: 'Persona kmu_ceo äußerte Bedenken.',
      quote: 'Persona kmu_ceo äußerte Bedenken.',
      source_id_anchor: 'web:https://example.com/x#:~:text=Anker-Tests',
    };
    const result = EvidenceItemSchema.safeParse(item);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.quote).toBe('Persona kmu_ceo äußerte Bedenken.');
      expect(result.data.source_id_anchor).toBe('web:https://example.com/x#:~:text=Anker-Tests');
    }
  });

  it('parses sample without optional fields (Task 12 backward compat)', () => {
    const item = {
      type: 'graph_fact',
      source: 'graph',
      snippet: 'Kein Zitat verfügbar.',
    };
    const result = EvidenceItemSchema.safeParse(item);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.quote).toBeUndefined();
      expect(result.data.source_id_anchor).toBeUndefined();
    }
  });

  it('parses section hypothesis without evidence as dedicated slot', () => {
    const result = ReportSectionHypothesisSchema.safeParse({
      hypothesis_id: 'hypothesis_02',
      hypothesis_text: 'Indizien legen einen weiteren Reibungspunkt nahe.',
      rationale: 'Die Ableitung ist plausibel, aber nicht direkt belegt.',
      suggested_evidence: ['zweite Stakeholder-Gruppe befragen'],
    });

    expect(result.success).toBe(true);
  });

  it('rejects malformed hypothesis_id', () => {
    const result = ReportSectionHypothesisSchema.safeParse({
      hypothesis_id: 'hyp_02',
      hypothesis_text: 'Indizien legen einen weiteren Reibungspunkt nahe.',
      rationale: 'Die Ableitung ist plausibel, aber nicht direkt belegt.',
      suggested_evidence: [],
    });

    expect(result.success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// ReportOutlineSchema — Regression-Tests für max-sections-Drift
// M11.4b-Followup-4: Zod hatte .max(5), Backend schon .max_length=15 seit Followup-2.
// Stub erzeugt 11 Pflichtabschnitte → Zod-Parse warf → ol.outline nie gerendert.
// ---------------------------------------------------------------------------
describe('ReportOutlineSchema (Drift-Guard max-sections)', () => {
  const makeSection = (title: string) => ({
    title,
    description: `Beschreibung für ${title}.`,
  });

  it('akzeptiert 11 Sections (Stub-Pflichtabschnitte)', () => {
    const outline = {
      title: 'Stub-Report',
      summary: 'Zusammenfassung.',
      sections: Array.from({ length: 11 }, (_, i) => makeSection(`Abschnitt ${i + 1}`)),
    };
    const result = ReportOutlineSchema.safeParse(outline);
    expect(result.success, `Zod lehnte 11 Sections ab: ${JSON.stringify(result)}`).toBe(true);
  });

  it('akzeptiert 15 Sections (Backend max_length=15)', () => {
    const outline = {
      title: 'Langer Report',
      summary: 'Zusammenfassung.',
      sections: Array.from({ length: 15 }, (_, i) => makeSection(`Abschnitt ${i + 1}`)),
    };
    expect(ReportOutlineSchema.safeParse(outline).success).toBe(true);
  });

  it('lehnt 16 Sections ab (über Backend-Grenze)', () => {
    const outline = {
      title: 'Zu langer Report',
      summary: 'Zusammenfassung.',
      sections: Array.from({ length: 16 }, (_, i) => makeSection(`Abschnitt ${i + 1}`)),
    };
    expect(ReportOutlineSchema.safeParse(outline).success).toBe(false);
  });

  it('lehnt leere sections-Liste ab (min=1)', () => {
    const outline = {
      title: 'Leerer Report',
      summary: 'Zusammenfassung.',
      sections: [],
    };
    expect(ReportOutlineSchema.safeParse(outline).success).toBe(false);
  });
});
