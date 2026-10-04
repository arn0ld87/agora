/**
 * Haltungsanalyse-Contract — Zod-Spiegel (Issue #1778, Schritt 1.8).
 *
 * Hand-gepflegt, 1:1 zu:
 *   schemas/stance-analysis.schema.json
 *
 * Änderungen am Pydantic-Modell
 * (backend/app/contracts/stance_analysis_contract.py)
 * → Schema-Dump → diese Datei synchronisieren.
 *
 * Regeln (gespiegelt aus dem Backend-Contract):
 *   - applicable=false heißt: der Lauf hat keine Streitfrage; Listen und
 *     Lagerverteilung sind dann leer, positioning_ratio ist null.
 *   - Eine Stimme ist positioniert, wenn mindestens einer ihrer Beiträge
 *     "in_favour" oder "opposed" ist.
 */
import { z } from "zod";

// === Literale (1:1 zum Pydantic-Contract) ===
export const StanceClassSchema = z.enum(["in_favour", "opposed", "undecided"]);
export type StanceClass = z.infer<typeof StanceClassSchema>;

// === ClassifiedContribution ===
export const ClassifiedContributionSchema = z
  .object({
    agent_id: z.number().int(),
    agent_name: z.string(),
    platform: z.string(),
    round_num: z.number().int(),
    action_type: z.string(),
    producer_key: z.string(),
    stance_class: StanceClassSchema,
  })
  .strict();
export type ClassifiedContribution = z.infer<
  typeof ClassifiedContributionSchema
>;

// === VoiceStance ===
export const VoiceStanceSchema = z
  .object({
    voice_key: z.string(),
    agent_name: z.string(),
    role_family: z.string().nullable().optional(),
    start_class: StanceClassSchema,
    contribution_classes: z.array(StanceClassSchema).default([]),
    interview_class: StanceClassSchema.nullable().optional(),
  })
  .strict();
export type VoiceStance = z.infer<typeof VoiceStanceSchema>;

// === StanceAnalysis (schemas/stance-analysis.schema.json) ===
export const StanceAnalysisSchema = z
  .object({
    contested_statement: z.string().nullable().optional(),
    applicable: z.boolean(),
    voices_total: z.number().int().min(0).default(0),
    voices_positioned: z.number().int().min(0).default(0),
    positioning_ratio: z.number().min(0).max(1).nullable().optional(),
    camp_distribution: z
      .partialRecord(StanceClassSchema, z.number().int())
      .default({}),
    voices: z.array(VoiceStanceSchema).default([]),
    contributions: z.array(ClassifiedContributionSchema).default([]),
    classified_total: z.number().int().min(0).default(0),
    classification_failed: z.number().int().min(0).default(0),
  })
  .strict();
export type StanceAnalysis = z.infer<typeof StanceAnalysisSchema>;
