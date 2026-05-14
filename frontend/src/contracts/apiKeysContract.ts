/**
 * API-Keys-Contract v1 — Zod-Spiegel.
 *
 * Hand-gepflegt, 1:1 zu schemas/api-key*.schema.json. Änderungen am
 * Pydantic-Modell (backend/app/contracts/api_keys_contract.py) →
 * Schema-Dump → diese Datei synchronisieren.
 */
import { z } from "zod";

// === ApiKeyScope ===
export const ApiKeyScopeSchema = z.enum(["read", "write", "admin"]);
export type ApiKeyScope = z.infer<typeof ApiKeyScopeSchema>;

// === ApiKeyStatus ===
export const ApiKeyStatusSchema = z.enum(["active", "revoked"]);
export type ApiKeyStatus = z.infer<typeof ApiKeyStatusSchema>;

// === ApiKeyModel (persistierte Repräsentation, ohne Klartext) ===
export const ApiKeyModelSchema = z
  .object({
    id: z.string().min(1),
    label: z.string().min(1).max(120),
    prefix: z
      .string()
      .min(12)
      .max(12)
      .regex(/^ago_[0-9a-f]{8}$/),
    scopes: z.array(ApiKeyScopeSchema).min(1),
    status: ApiKeyStatusSchema,
    hashed_token: z.string(),
    created_at: z.string(),
    last_used_at: z.string().nullable().optional(),
    revoked_at: z.string().nullable().optional(),
  })
  .strict();
export type ApiKeyModel = z.infer<typeof ApiKeyModelSchema>;

// === ApiKeyCreateRequest ===
export const ApiKeyCreateRequestSchema = z
  .object({
    label: z.string().min(1).max(120),
    scopes: z.array(ApiKeyScopeSchema).min(1),
  })
  .strict();
export type ApiKeyCreateRequest = z.infer<typeof ApiKeyCreateRequestSchema>;

// === ApiKeyCreateResponse (Klartext-Token erscheint hier genau einmal) ===
export const ApiKeyCreateResponseSchema = z
  .object({
    key: ApiKeyModelSchema,
    token: z.string().regex(/^ago_[0-9a-f]{48}$/),
  })
  .strict();
export type ApiKeyCreateResponse = z.infer<typeof ApiKeyCreateResponseSchema>;

// === ApiKeysListResponse ===
export const ApiKeysListResponseSchema = z
  .object({
    items: z.array(ApiKeyModelSchema),
    total: z.number().int().min(0),
  })
  .strict();
export type ApiKeysListResponse = z.infer<typeof ApiKeysListResponseSchema>;
