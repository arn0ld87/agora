/**
 * LLM-Provider-API-Keys Contract — Zod-Spiegel.
 *
 * Spiegelt backend/app/contracts/llm_provider_keys_contract.py 1:1.
 * Klartext-Keys werden im Frontend NIE aus der Antwort gelesen — nur
 * maskierte Werte (sk-...abcd) treten hier auf.
 */
import { z } from "zod";

export const MASKED_KEY_PATTERN = /^.{1,8}\.\.\.[A-Za-z0-9_\-]{4}$/;

export const LlmProviderKeyEntrySchema = z
  .object({
    provider_id: z.string().min(1).max(64),
    masked_value: z.string().regex(MASKED_KEY_PATTERN),
    base_url: z.string().nullable().optional(),
    created_at: z.string(),
    updated_at: z.string(),
    last_validated_at: z.string().nullable().optional(),
    last_validation_ok: z.boolean().nullable().optional(),
  })
  .strict();
export type LlmProviderKeyEntry = z.infer<typeof LlmProviderKeyEntrySchema>;

export const LlmProviderKeyCreateRequestSchema = z
  .object({
    api_key: z.string().min(4).max(1024),
    base_url: z.string().max(512).nullable().optional(),
  })
  .strict();
export type LlmProviderKeyCreateRequest = z.infer<typeof LlmProviderKeyCreateRequestSchema>;

export const LlmProviderKeysListResponseSchema = z
  .object({
    items: z.array(LlmProviderKeyEntrySchema),
    total: z.number().int().min(0),
  })
  .strict();
export type LlmProviderKeysListResponse = z.infer<typeof LlmProviderKeysListResponseSchema>;
