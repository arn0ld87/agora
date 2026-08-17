/**
 * Report-Contract v2 — Zod-Spiegel.
 *
 * Hand-gepflegt, aber 1:1 zu schemas/report-contract.schema.json.
 * CI prüft Drift via Vitest: Frontend-Zod parst Sample-Payloads aus Backend.
 *
 * Änderung an Pydantic-Modellen → Backend dumpen → diese Datei sync.
 */
import { z } from "zod";

/**
 * ADR-0002: Claims brauchen mindestens ein stützendes Evidence-Item.
 * Eine einzelne Quelle trägt höchstens einen low Claim; ohne Quelle routet
 * das Backend die Aussage zur Hypothesis.
 */
export const CLAIM_MIN_EVIDENCE_FOR_CLAIM = 1;

// === Enums ===
export const ConfidenceLabelSchema = z.enum(["speculative", "low", "medium", "high", "verified"]);
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
  "seed_document",
  "model_generated_inference", // im audit_trail erlaubt, in evidence verboten
]);
export type EvidenceType = z.infer<typeof EvidenceTypeSchema>;

// ADR-0002 Anker 3 (Sub-Slice M11.7b): Quellengattung pro Evidence-Item.
// Spiegelt EvidenceSourceKind aus backend/app/contracts/report_contract.py.
// Report-Trust-Slice: um "agent_action" und "web_source" erweitert, damit
// Seed-Dokument, Simulation und Web-Recherche nicht mehr in einer einzigen
// Gattung verschmelzen.
export const EvidenceSourceKindSchema = z.enum([
  "seed_corpus",
  "agent_quote",
  "agent_action",
  "graph_relation",
  "web_source",
  "inferred",
]);
export type EvidenceSourceKind = z.infer<typeof EvidenceSourceKindSchema>;

// Quellengattungen aus der Simulation — nie ein Seed-Fakt.
// Pendant zu SIMULATION_SOURCE_KINDS im Backend.
export const SIMULATION_SOURCE_KINDS: ReadonlySet<EvidenceSourceKind> = new Set([
  "agent_quote",
  "agent_action",
]);

// Urteil der zweiten Binding-Stufe. Spiegelt EntailmentVerdict aus
// backend/app/services/evidence_entailment.py. Nur "SUPPORTED" darf
// supports_claim=true begruenden — Retrieval-Aehnlichkeit allein nicht.
export const EntailmentVerdictSchema = z.enum([
  "SUPPORTED",
  "CONTRADICTED",
  "RELATED_ONLY",
  "INSUFFICIENT",
]);
export type EntailmentVerdict = z.infer<typeof EntailmentVerdictSchema>;

export const EvidenceIdSchema = z.string().regex(/^ev_[0-9a-f]{32}$/);
export type EvidenceId = z.infer<typeof EvidenceIdSchema>;

export const ReportStatusSchema = z.enum([
  "pending", "planning", "generating", "incomplete", "completed", "failed",
]);

const FORBIDDEN_EVIDENCE_TYPES = new Set(["model_generated_inference", "section_synthesis"]);

// === Sub-Modelle ===
export const AgentLogRefSchema = z.object({
  section_index: z.number().int().min(0),
  action: z.string(),
  tool_name: z.string().optional().nullable(),
}).strict();

const EvidenceSourceSchema = z.object({
  type: EvidenceTypeSchema,
  source: z.string().min(1),
  snippet: z.string().min(1).max(2000),
  value: z.union([z.string(), z.number(), z.boolean()]).optional().nullable(),
  tool_name: z.string().optional().nullable(),
  query: z.string().optional().nullable(),
  raw: z.unknown().optional().nullable(),
  agent_log_ref: AgentLogRefSchema.optional().nullable(),
  // MAI-14 (backend) + Sub-Slice 05.8 (Zod-Spiegel):
  // Sentiment des Quellen-Snippets (-1 negativ, 0 neutral, +1 positiv).
  // confidence_calculator._has_contradiction nutzt es, um widersprüchliche
  // Sentiment-Vektoren zu erkennen. Pendant zu EvidenceItemModel.sentiment_score.
  sentiment_score: z.number().min(-1).max(1).optional().nullable(),
  quote: z.string().min(1).max(500).optional().nullable(),
  source_id_anchor: z.string().min(1).max(200).optional().nullable(),
  // ADR-0002 Anker 3 (Sub-Slice M11.7b). Default "inferred": unbekannte
  // Herkunft ist abgeleitet, nicht belegt. Spiegelt den Backend-Default.
  source_kind: EvidenceSourceKindSchema.default("inferred"),
  persona_stakeholder_group: z.string().min(1).max(200).optional().nullable(),
  persona_role_family: z.string().min(1).max(120).optional().nullable(),
  // Slice 8 (2026-05-16) — Provider+Modell, das diese Evidence-Zeile
  // extrahiert hat. Pendant zu EvidenceItemModel.source_model. Format
  // "<provider>/<model_id>" (z. B. "ollama/qwen2.5:32b"). None bei
  // Pre-Slice-8-Daten — daher .nullable().optional().
  source_model: z.string().max(200).nullable().optional(),
}).strict();

const validateEvidenceSource = (
  value: {
    type: string;
    source_kind: string;
    persona_stakeholder_group?: string | null;
  },
  ctx: z.RefinementCtx,
) => {
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
};

export const EvidenceItemSchema = EvidenceSourceSchema.superRefine(validateEvidenceSource);
export type EvidenceItem = z.infer<typeof EvidenceItemSchema>;

export const EvidenceRecordSchema = EvidenceSourceSchema.extend({
  evidence_id: EvidenceIdSchema,
  producer_key: z.string().min(1),
}).superRefine(validateEvidenceSource);
export type EvidenceRecord = z.infer<typeof EvidenceRecordSchema>;

export const ClaimEvidenceBindingSchema = z.object({
  evidence_id: EvidenceIdSchema,
  // Compatibility-Alias für bestehende Persistenz; beide Scores bleiben
  // claim-relativ und gehören deshalb nicht in den EvidenceRecord.
  match_score: z.number().min(0).max(1).optional().nullable(),
  retrieval_score: z.number().min(0).max(1).optional().nullable(),
  entailment: EntailmentVerdictSchema.optional().nullable(),
  entailment_reason: z.string().max(500).optional().nullable(),
  supports_claim: z.boolean().optional().nullable(),
  contradicts_claim: z.boolean().optional().nullable(),
}).strict();
export type ClaimEvidenceBinding = z.infer<typeof ClaimEvidenceBindingSchema>;

export const EvidenceIndexSchema = z
  .record(EvidenceIdSchema, EvidenceRecordSchema)
  .superRefine((index, ctx) => {
    for (const [key, record] of Object.entries(index)) {
      if (key !== record.evidence_id) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: [key, 'evidence_id'],
          message: `Evidence-Index-Key '${key}' stimmt nicht mit evidence_id '${record.evidence_id}' überein.`,
        });
      }
    }
  });
export type EvidenceIndex = z.infer<typeof EvidenceIndexSchema>;

export const ReportClaimSchema = z.object({
  claim_id: z.string().regex(/^claim_\d{2,}$/),
  claim_text: z.string().min(8),
  confidence_label: ConfidenceLabelSchema,
  confidence_score: z.number().min(0).max(1),
  evidence: z.array(ClaimEvidenceBindingSchema).max(10).default([]),
  audit_trail: z.array(z.record(z.string(), z.unknown())).default([]),
  notes: z.string().optional().nullable(),
}).strict().superRefine((value, ctx) => {
  const supportingEvidenceCount = value.evidence.filter(
    (binding) => binding.supports_claim === true,
  ).length;
  if (supportingEvidenceCount < CLAIM_MIN_EVIDENCE_FOR_CLAIM) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: `Label '${value.confidence_label}' verlangt mindestens ${CLAIM_MIN_EVIDENCE_FOR_CLAIM} stützende Evidence.`,
    });
  }
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
});
export type ReportClaim = z.infer<typeof ReportClaimSchema>;

export const ReportSectionHypothesisSchema = z.object({
  hypothesis_id: z.string().regex(/^hypothesis_\d{2,}$/),
  hypothesis_text: z.string().min(8).max(1000),
  rationale: z.string().min(8).max(1000),
  suggested_evidence: z.array(z.string()).max(5).default([]),
}).strict();
export type ReportSectionHypothesis = z.infer<typeof ReportSectionHypothesisSchema>;

export const ReportSectionDataGapSchema = z.object({
  gap_id: z.string().regex(/^gap_\d{2,}$/),
  claim_text: z.string().min(8).max(1000),
  gap_reason: z.string().min(1).max(200),
  suggested_fix: z.string().min(1).max(500).optional().nullable(),
  // Issue #1319: Verweis auf die Hypothese, aus der die Datenlücke entstand.
  // Optional, weil der zweite Erzeuger (medium/high ohne Evidence) keine
  // begleitende Hypothese anlegt. Das Schema ist `.strict()` — ohne diesen
  // Eintrag würde der Spiegel das neue Backend-Feld zurückweisen.
  hypothesis_id: z.string().regex(/^hypothesis_\d{2,}$/).optional().nullable(),
}).strict();
export type ReportSectionDataGap = z.infer<typeof ReportSectionDataGapSchema>;

// Issue #1356: eine im Fliesstext belassene, unbelegte Faktenaussage.
// Spiegelt backend ReportSectionUnverifiedStatementModel. Abgrenzung zur
// Hypothese: die Hypothese ist die herausgeloeste Behauptung samt Vorschlag,
// wie sie zu belegen waere — dieses Objekt beschreibt, was im gelesenen Text
// mit welcher Einschraenkung stehengeblieben ist.
export const ReportSectionUnverifiedStatementSchema = z.object({
  statement_text: z.string().min(1).max(1000),
  verdict: z.string().min(1).max(32),
  reason: z.string().min(1).max(200),
}).strict();
export type ReportSectionUnverifiedStatement = z.infer<
  typeof ReportSectionUnverifiedStatementSchema
>;

export const ReportSectionSchema = z.object({
  section_index: z.number().int().min(1),
  section_title: z.string().min(3),
  section_summary: z.string().min(1),
  claims: z.array(ReportClaimSchema).default([]),
  hypotheses: z.array(ReportSectionHypothesisSchema).default([]),
  // Slice 3 (Issue #495): Überhang nach Cap von 5 — spiegelt backend ReportSectionModel.hypotheses_appendix.
  hypotheses_appendix: z.array(ReportSectionHypothesisSchema).max(50).default([]),
  data_gaps: z.array(ReportSectionDataGapSchema).default([]),
  // P0-6: Von generate_section_metadata extrahierte ReportV3-Strukturdaten.
  // Sie sind die kanonische Quelle fuer Personas/Segmente/Reibungspunkte in
  // ReportV3 — bewusst unstrukturiert, die Einzel-DTOs validiert das Backend.
  structured_metadata: z.record(z.string(), z.unknown()).default({}),
  // P0-7: true, wenn dieser Abschnitt nur Fallback-/Fehlertext enthaelt.
  generation_failed: z.boolean().default(false),
  // Issue #1324: zitierte, aber nie gebundene Evidence-Refs des Abschnitts.
  unbound_evidence_refs: z.array(z.string()).default([]),
  // Issue #1356: Aussagen, die im Fliesstext stehen geblieben sind, fuer die
  // sich aber kein Beleg fand. Sie tragen dort den sichtbaren Marker
  // "[Beleg fehlt]"; hier steht dieselbe Information strukturiert, damit die
  // UI nicht am Markerstring parsen muss.
  unverified_statements: z.array(ReportSectionUnverifiedStatementSchema).max(200).default([]),
}).strict();
export type ReportSection = z.infer<typeof ReportSectionSchema>;

export const ReportOutlineSectionSchema = z.object({
  title: z.string().min(3),
  // max(2000) — spiegelt backend/app/contracts/report_contract.py
  // (Smoke-Live 2026-05-15: 500 brach reale Outline-Beschreibungen).
  description: z.string().min(1).max(2000),
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

/**
 * Issue #1192: Stand der Simulation zum Startzeitpunkt der Reportgenerierung.
 *
 * Spiegelt `SimulationSnapshotModel` aus
 * `backend/app/contracts/report_contract.py`. Ein Report darf auf einem
 * Zwischenstand beruhen — er muss nur ausweisen, dass er es tut.
 */
export const SimulationSnapshotSchema = z.object({
  rounds_completed: z.number().int().min(0),
  total_rounds: z.number().int().min(0).default(0),
  simulation_running: z.boolean().default(false),
  captured_at: z.string().optional().nullable(),
}).strict();
export type SimulationSnapshot = z.infer<typeof SimulationSnapshotSchema>;

export const ReportSchema = z.object({
  schema_version: z.literal(2),
  report_id: z.string().min(1),
  simulation_id: z.string().min(1),
  graph_id: z.string().min(1),
  simulation_requirement: z.string().min(1),
  status: ReportStatusSchema,
  outline: ReportOutlineSchema.optional().nullable(),
  markdown_content: z.string().default(""),
  missing_sections: z.array(z.string()).default([]),
  created_at: z.string().optional().nullable(),
  completed_at: z.string().optional().nullable(),
  error: z.string().optional().nullable(),
  has_evidence: z.boolean().default(false),
  evidence_sections: z.number().int().min(0).default(0),
  red_team_findings: z.array(z.string()).max(10).default([]),
  // Issue #1192: Simulationsstand zum Startzeitpunkt des Reports. Nullable
  // mit Default — Bestandsreports ohne den Slot bleiben gültig.
  simulation_snapshot: SimulationSnapshotSchema.optional().nullable(),
}).strict();
export type Report = z.infer<typeof ReportSchema>;

/**
 * Protokoll einer lokalen Claim-Degradierung (Issue #1006).
 *
 * Ein einzelner ADR-0002-Verstoß beendet den Report nicht mehr als `failed`;
 * der verletzende Claim wird lokal abgestuft und die Reparatur hier
 * festgehalten. `action` ist einer von "downgraded_to_low",
 * "moved_to_hypotheses" oder "dropped" — bewusst als String gespiegelt, weil
 * das Backend dafür ebenfalls keinen Enum führt.
 */
export const EvidenceDegradationSchema = z.object({
  section_index: z.number().int(),
  claim_id: z.string(),
  violation: z.string(),
  action: z.string(),
  detail: z.string(),
}).strict();
export type EvidenceDegradation = z.infer<typeof EvidenceDegradationSchema>;

export const EvidenceMapSchema = z.object({
  schema_version: z.literal(3),
  report_id: z.string().min(1),
  simulation_id: z.string().min(1),
  evidence_index: EvidenceIndexSchema,
  global_evidence_refs: z.array(EvidenceIdSchema).default([]),
  sections: z.array(ReportSectionSchema).default([]),
  // Additiv mit Default: persistierte Evidence-Maps von vor #1006 tragen das
  // Feld nicht und müssen weiterhin parsen.
  degradation_log: z.array(EvidenceDegradationSchema).default([]),
  // PR #1151: Audit-Trail regulärer Gate-Entscheidungen (fehlende Evidence,
  // fehlende Supporting-Evidence, Fließtext-Entfernungen). Getrennt vom
  // degradation_log, weil nur Letzterer den Report-Status abstuft.
  gate_decision_log: z.array(EvidenceDegradationSchema).default([]),
}).strict().superRefine((value, ctx) => {
  const knownIds = new Set(Object.keys(value.evidence_index));
  const checkRef = (evidenceId: string, path: PropertyKey[]) => {
    if (!knownIds.has(evidenceId)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path,
        message: `Unbekannte evidence_id '${evidenceId}'.`,
      });
    }
  };

  value.global_evidence_refs.forEach((evidenceId, index) => {
    checkRef(evidenceId, ['global_evidence_refs', index]);
  });

  value.sections.forEach((section, sectionIndex) => {
    section.claims.forEach((claim, claimIndex) => {
      claim.evidence.forEach((binding, bindingIndex) => {
        checkRef(binding.evidence_id, [
          'sections',
          sectionIndex,
          'claims',
          claimIndex,
          'evidence',
          bindingIndex,
          'evidence_id',
        ]);
      });

      if (claim.confidence_label === 'high' || claim.confidence_label === 'verified') {
        const boundRecords = claim.evidence
          .map((binding) => value.evidence_index[binding.evidence_id])
          .filter((record): record is EvidenceRecord => record !== undefined);
        const supportingRecords = claim.evidence
          .filter((binding) => binding.supports_claim === true)
          .map((binding) => value.evidence_index[binding.evidence_id])
          .filter((record): record is EvidenceRecord => record !== undefined);
        const stakeholderGroups = new Set(
          supportingRecords
            .filter((record) => record.source_kind === 'agent_quote')
            .map((record) => record.persona_stakeholder_group)
            .filter((group): group is string => group !== undefined && group !== null),
        );
        if (stakeholderGroups.size < 2) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ['sections', sectionIndex, 'claims', claimIndex, 'evidence'],
            message: `Label '${claim.confidence_label}' verlangt unterstützende agent_quote-Evidence aus mindestens 2 unterschiedlichen Stakeholder-Gruppen.`,
          });
        }
        if (boundRecords.some((record) => record.source_kind === 'inferred')) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ['sections', sectionIndex, 'claims', claimIndex, 'evidence'],
            message: `Label '${claim.confidence_label}' duldet keine source_kind=inferred-Evidence.`,
          });
        }
      }
    });
  });
});
export type EvidenceMap = z.infer<typeof EvidenceMapSchema>;

/**
 * Spiegel zu `EvidenceOmissionModel` (Issue #987).
 *
 * Gesetzt genau dann, wenn eine Evidence-Map vorlag, aber den Vertrag auch
 * nach der Migration verletzte und deshalb nicht mit exportiert wurde. Ohne
 * dieses Feld war ein entleerter Envelope von einem Report ohne Evidence
 * nicht zu unterscheiden — beide lieferten schlicht `evidence: null`.
 *
 * `reason` ist der stabile Schluessel, aus dem die Oberflaeche per vue-i18n
 * uebersetzt. `detail` ist bewusst KEIN UI-String: es erklaert den fehlenden
 * Evidence-Teil demjenigen, der die exportierte Datei spaeter ohne Agora
 * oeffnet. Nicht rendern — sonst haengt die Anzeigesprache am Backend.
 */
export const EvidenceOmissionSchema = z.object({
  reason: z.literal('contract_violation'),
  detail: z.string().min(1),
  validation_errors: z.array(z.string()).max(5).default([]),
}).strict();
export type EvidenceOmission = z.infer<typeof EvidenceOmissionSchema>;

export const ReportContractSchema = z.object({
  schema_version: z.literal(2),
  exported_at: z.string().datetime(),
  report: ReportSchema,
  evidence: EvidenceMapSchema.optional().nullable(),
  // Additiv mit Default null: Envelopes von vor #987 tragen das Feld nicht.
  evidence_omitted: EvidenceOmissionSchema.optional().nullable().default(null),
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
