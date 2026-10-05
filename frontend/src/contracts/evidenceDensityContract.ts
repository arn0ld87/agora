/**
 * Belegdichte-Contract — Zod-Spiegel (Issue #1779, Schritt 2.1).
 *
 * Hand-gepflegt, 1:1 zu:
 *   schemas/evidence-density.schema.json
 *
 * Änderungen am Pydantic-Modell
 * (backend/app/contracts/evidence_density_contract.py)
 * → Schema-Dump → diese Datei synchronisieren.
 *
 * Regeln (gespiegelt aus dem Backend-Contract):
 *   - claims_without_support + claims_single_support + claims_multi_support
 *     ergeben claims_total.
 *   - Die Quoten sind null, wenn der Bericht keine Claims hat.
 */
import { z } from "zod";

// === EvidenceDensity (schemas/evidence-density.schema.json) ===
export const EvidenceDensitySchema = z
  .object({
    schema_version: z.number().int().default(1),
    claims_total: z.number().int().min(0).default(0),
    claims_without_support: z.number().int().min(0).default(0),
    claims_single_support: z.number().int().min(0).default(0),
    claims_multi_support: z.number().int().min(0).default(0),
    claims_multi_independent: z.number().int().min(0).default(0),
    claims_at_single_source_cap: z.number().int().min(0).default(0),
    claims_with_action_support: z.number().int().min(0).default(0),
    supporting_links_by_type: z.record(z.string(), z.number().int()).default({}),
    single_support_ratio: z.number().min(0).max(1).nullable().optional(),
    action_support_ratio: z.number().min(0).max(1).nullable().optional(),
    single_source_cap_ratio: z.number().min(0).max(1).nullable().optional(),
    multi_independent_ratio: z.number().min(0).max(1).nullable().optional(),
  })
  .strict()
  .refine(
    (d) =>
      d.claims_without_support +
        d.claims_single_support +
        d.claims_multi_support ===
      d.claims_total,
    {
      message:
        "claims_without_support + claims_single_support + claims_multi_support muss claims_total ergeben",
    },
  );
export type EvidenceDensity = z.infer<typeof EvidenceDensitySchema>;
