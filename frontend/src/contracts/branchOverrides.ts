/**
 * Branch-Override-Contract — Zod-Spiegel (Issue #886).
 *
 * Hand-gepflegt, 1:1 zu backend/app/contracts/branch_request_contract.py und
 * schemas/branch-overrides.schema.json. Feld- und Typnamen spiegeln die
 * historische Whitelist in branching_service.py::create_branch
 * (allowed_override_keys).
 *
 * ai_model_ref ist die kanonische (Provider-Connection, Modell)-Referenz.
 * llm_model bleibt als deprecated Legacy-Key erhalten — beide zusammen sind
 * ungueltig, gespiegelt vom Backend-model_validator
 * (_reject_ai_model_ref_with_legacy_llm_model).
 *
 * Änderungen am Pydantic-Modell → Schema-Dump → diese Datei synchronisieren.
 */
import { z } from 'zod'

import { AiModelSourceSchema } from './aiModelRef'

// Wie ReplayAiModelRefSchema (runManifestContract.ts): source hat
// backendseitig einen Default ("explicit") und ist deshalb hier optional.
export const BranchAiModelRefSchema = z
  .object({
    provider_connection_id: z.string().min(1),
    model_id: z.string().min(1),
    source: AiModelSourceSchema.optional(),
    capability_filter: z.string().nullable().optional(),
    fallback_reason: z.string().nullable().optional(),
  })
  .strict()

// Ungerefinte Basis fuer den Feld-Spiegel-Test (branchOverridesContract.spec.ts)
// — analog ProviderConnectionBaseSchema in aiProviderContract.ts. `.refine()`
// kapselt die Shape hinter ZodEffects; der Test braucht den direkten Zugriff.
export const BranchOverridesBaseSchema = z
  .object({
    llm_model: z.string().nullable().optional(),
    language: z.string().nullable().optional(),
    max_agents: z.number().int().nullable().optional(),
    time_config: z.record(z.string(), z.unknown()).nullable().optional(),
    enable_twitter: z.boolean().nullable().optional(),
    enable_reddit: z.boolean().nullable().optional(),
    persona_additions: z
      .array(z.record(z.string(), z.unknown()))
      .nullable()
      .optional(),
    persona_removals: z.array(z.string()).nullable().optional(),
    ai_model_ref: BranchAiModelRefSchema.nullable().optional(),
  })
  .strict()

export const BranchOverridesSchema = BranchOverridesBaseSchema.refine(
  (value) => !(value.ai_model_ref && value.llm_model),
  {
    message: 'ai_model_ref darf nicht mit llm_model kombiniert werden',
    path: ['ai_model_ref'],
  },
)
export type BranchOverrides = z.infer<typeof BranchOverridesSchema>
