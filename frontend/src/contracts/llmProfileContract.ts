/**
 * LLM-Profile-Contract — Zod-Spiegel zu backend/app/contracts/llm_profile_contract.py
 * P5.1 Layer 0. Spiegelt LlmProfile, LlmProfileListResponse, LlmProfileCreateRequest.
 */
import { z } from "zod";

export const LlmProviderSchema = z.enum([
  "ollama",
  "openai",
  "google",
  "gemini",
  "anthropic",
  "custom",
  "ollama_cloud",
  "openai_compatible",
  "minimax",
  "opencode_go",
  "github_copilot",
  "bedrock",
  "cloud",
  "codex_cli",
  "unknown",
]);
export type LlmProvider = z.infer<typeof LlmProviderSchema>;

export const LlmProfileSchema = z
  .object({
    id: z.string(),
    name: z.string().min(1).max(80),
    provider: LlmProviderSchema,
    base_url: z.string().min(1),
    model_name: z.string().min(1),
    // null = nicht gesetzt (Update lässt Feld weg). "" = explizit geleert.
    api_key: z.string().nullable().default(null),
    is_default: z.boolean().default(false),
    created_at: z.string(), // ISO-String (datetime serialisiert als str)
    updated_at: z.string(),
  })
  .strict();
export type LlmProfile = z.infer<typeof LlmProfileSchema>;

export const LlmProfileListResponseSchema = z
  .object({
    profiles: z.array(LlmProfileSchema),
  })
  .strict();
export type LlmProfileListResponse = z.infer<typeof LlmProfileListResponseSchema>;

export const LlmProfileCreateRequestSchema = z
  .object({
    name: z.string().min(1).max(80),
    provider: LlmProviderSchema,
    base_url: z.string().min(1),
    model_name: z.string().min(1),
    api_key: z.string().nullable().default(null),
    is_default: z.boolean().default(false),
  })
  .strict();
export type LlmProfileCreateRequest = z.infer<typeof LlmProfileCreateRequestSchema>;
