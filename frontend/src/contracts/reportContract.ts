/**
 * Report-Contract v2 — Zod-Spiegel.
 *
 * Hand-gepflegt, aber 1:1 zu schemas/report-contract.schema.json.
 * CI prüft Drift via Vitest: Frontend-Zod parst Sample-Payloads aus Backend.
 *
 * Änderung an Pydantic-Modellen → Backend dumpen → diese Datei sync.
 */
import { z } from "zod";

// === Enums ===
export const ConfidenceLabelSchema = z.enum(["low", "medium", "high", "verified"]);
export type ConfidenceLabel = z.infer<typeof ConfidenceLabelSchema>;

export const EvidenceTypeSchema = z.enum([
  "graph_fact",
  "graph_metric",
  "graph_metric_status",
  "relationship_chain",
  "entity_summary",
  "agent_action",
  "agent_interview",
  "web_search_result",
  "web_fetch",
  "model_generated_inference", // im audit_trail erlaubt, in evidence verboten
]);
export type EvidenceType = z.infer<typeof EvidenceTypeSchema>;

// ADR-0002 Anker 3 (Sub-Slice M11.7b): Quellengattung pro Evidence-Item.
// Spiegelt EvidenceSourceKind aus backend/app/contracts/report_contract.py.
export const EvidenceSourceKindSchema = z.enum([
  "seed_corpus",
  "agent_quote",
  "graph_relation",
  "inferred",
]);
export type EvidenceSourceKind = z.infer<typeof EvidenceSourceKindSchema>;

export const ReportStatusSchema = z.enum([
  "pending", "planning", "generating", "completed", "failed",
]);

const FORBIDDEN_EVIDENCE_TYPES = new Set(["model_generated_inference", "section_synthesis"]);

// === Sub-Modelle ===
export const AgentLogRefSchema = z.object({
  section_index: z.number().int().min(0),
  action: z.string(),
  tool_name: z.string().optional().nullable(),
}).strict();

export const EvidenceItemSchema = z.object({
  type: EvidenceTypeSchema,
  source: z.string().min(1),
  snippet: z.string().min(1).max(2000),
  value: z.union([z.string(), z.number(), z.boolean()]).optional().nullable(),
  tool_name: z.string().optional().nullable(),
  query: z.string().optional().nullable(),
  raw: z.unknown().optional().nullable(),
  agent_log_ref: AgentLogRefSchema.optional().nullable(),
  match_score: z.number().min(0).max(1).optional().nullable(),
  supports_claim: z.boolean().optional().nullable(),
  quote: z.string().min(1).max(500).optional().nullable(),
  source_id_anchor: z.string().min(1).max(200).optional().nullable(),
  // ADR-0002 Anker 3 (Sub-Slice M11.7b)
  source_kind: EvidenceSourceKindSchema.default("seed_corpus"),
  persona_stakeholder_group: z.string().min(1).max(200).optional().nullable(),
}).strict().superRefine((value, ctx) => {
  // Spiegelt EvidenceItemModel.reject_inference_in_evidence
  if (FORBIDDEN_EVIDENCE_TYPES.has(value.type)) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: `EvidenceType '${value.type}' nur im audit_trail erlaubt, nicht in evidence.`,
    });
  }
  // ADR-0002 Anker 3 (Sub-Slice M11.7b): agent_quote braucht Stakeholder-Gruppe.
  if (value.source_kind === "agent_quote" && !value.persona_stakeholder_group) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: "source_kind=agent_quote verlangt persona_stakeholder_group.",
    });
  }
});
export type EvidenceItem = z.infer<typeof EvidenceItemSchema>;

export const ReportClaimSchema = z.object({
  claim_id: z.string().regex(/^claim_\d{2,}$/),
  claim_text: z.string().min(8),
  confidence_label: ConfidenceLabelSchema,
  confidence_score: z.number().min(0).max(1),
  evidence: z.array(EvidenceItemSchema).max(10).default([]),
  audit_trail: z.array(z.record(z.string(), z.unknown())).default([]),
  notes: z.string().optional().nullable(),
}).strict().superRefine((value, ctx) => {
  // Spiegelt ReportClaimModel.verified_needs_strong_match
  if (value.confidence_label === "verified") {
    const top = Math.max(0, ...value.evidence.map((e) => e.match_score ?? 0));
    if (top < 0.85) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `Label 'verified' verlangt match_score >= 0.85, top=${top.toFixed(2)}`,
      });
    }
  }
  // Spiegelt ReportClaimModel.reject_orphan_high_confidence
  if (value.confidence_label === "high" || value.confidence_label === "verified") {
    if (!value.evidence.some((e) => e.supports_claim === true)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `Label '${value.confidence_label}' verlangt mindestens eine Evidence mit supports_claim=true`,
      });
    }
  }
  // ADR-0002 Anker 4 (Sub-Slice M11.7b): high/verified verlangt agent_quote-
  // Evidence aus mindestens 2 unterschiedlichen Stakeholder-Gruppen.
  // Nur supports_claim=true zählt — widersprechende Quotes dürfen ein
  // high-Label nicht rechtfertigen (Gemini-Followup PR #343).
  if (value.confidence_label === "high" || value.confidence_label === "verified") {
    const groups = new Set(
      value.evidence
        .filter(
          (e) =>
            e.source_kind === "agent_quote"
            && e.supports_claim === true
            && e.persona_stakeholder_group,
        )
        .map((e) => e.persona_stakeholder_group as string),
    );
    if (groups.size < 2) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `Label '${value.confidence_label}' verlangt unterstützende agent_quote-Evidence (supports_claim=true) aus mindestens 2 unterschiedlichen Stakeholder-Gruppen. Gefunden: ${groups.size === 0 ? "∅" : Array.from(groups).sort().join(", ")}.`,
      });
    }
  }
  // ADR-0002 Anker 5 (Sub-Slice M11.7b): high/verified duldet keine inferred-Evidence.
  if (value.confidence_label === "high" || value.confidence_label === "verified") {
    if (value.evidence.some((e) => e.source_kind === "inferred")) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `Label '${value.confidence_label}' duldet keine source_kind=inferred-Evidence.`,
      });
    }
  }
});
export type ReportClaim = z.infer<typeof ReportClaimSchema>;

export const ReportSectionSchema = z.object({
  section_index: z.number().int().min(1),
  section_title: z.string().min(3),
  section_summary: z.string().min(1),
  claims: z.array(ReportClaimSchema).min(1),
}).strict();
export type ReportSection = z.infer<typeof ReportSectionSchema>;

export const ReportOutlineSectionSchema = z.object({
  title: z.string().min(3),
  description: z.string().min(1).max(500),
}).strict();

export const ReportOutlineSchema = z.object({
  title: z.string().min(3),
  summary: z.string().min(1),
  // M11.4b-Followup-4: max auf 15 angehoben — spiegelt backend/app/contracts/report_contract.py
  // ReportOutlineModel.sections (min_length=1, max_length=15, angehoben in M11.4b-Followup-2).
  // War 5: Stub liefert 11 Pflichtabschnitte, Zod-Parse warf → schemaError gesetzt →
  // reportOutline blieb null → ol.outline nie gerendert → E2E-Smoke schlug fehl.
  sections: z.array(ReportOutlineSectionSchema).min(1).max(15),
}).strict();
export type ReportOutline = z.infer<typeof ReportOutlineSchema>;

export const ReportSchema = z.object({
  schema_version: z.literal(2),
  report_id: z.string().min(1),
  simulation_id: z.string().min(1),
  graph_id: z.string().min(1),
  simulation_requirement: z.string().min(1),
  status: ReportStatusSchema,
  outline: ReportOutlineSchema.optional().nullable(),
  markdown_content: z.string().default(""),
  created_at: z.string().optional().nullable(),
  completed_at: z.string().optional().nullable(),
  error: z.string().optional().nullable(),
  has_evidence: z.boolean().default(false),
  evidence_sections: z.number().int().min(0).default(0),
}).strict();
export type Report = z.infer<typeof ReportSchema>;

export const EvidenceMapSchema = z.object({
  schema_version: z.literal(2),
  report_id: z.string().min(1),
  simulation_id: z.string().min(1),
  global_evidence: z.array(EvidenceItemSchema).default([]),
  sections: z.array(ReportSectionSchema).default([]),
}).strict();
export type EvidenceMap = z.infer<typeof EvidenceMapSchema>;

export const ReportContractSchema = z.object({
  schema_version: z.literal(2),
  exported_at: z.string().datetime(),
  report: ReportSchema,
  evidence: EvidenceMapSchema.optional().nullable(),
}).strict();
export type ReportContract = z.infer<typeof ReportContractSchema>;

/**
 * Strikte Parse-Funktion für Step4Report.vue — ersetzt den toleranten Renderer.
 * Bei Fehler: strukturierte Fehler zeigen, NICHT mit `?.` weiterrendern.
 */
export function parseReportContract(raw: unknown):
  | { ok: true; data: ReportContract }
  | { ok: false; errors: z.ZodIssue[] } {
  const result = ReportContractSchema.safeParse(raw);
  return result.success ? { ok: true, data: result.data } : { ok: false, errors: result.error.issues };
}
