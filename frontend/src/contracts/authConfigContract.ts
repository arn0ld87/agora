/**
 * Canonical Zod mirror of AuthConfigResponse in backend/app/contracts/workspace_contract.py.
 *
 * Mirrors `GET /api/auth/config` — öffentlich, ohne Geheimnisse (#1616).
 * `supabase_anon_key` ist der öffentliche Anon-Key; er ist für den Browser
 * bestimmt und gewährt allein keinen Zugriff auf Agora-Daten.
 */
import { z } from 'zod'

export const AuthConfigResponseSchema = z
  .object({
    auth_backend: z.string(),
    jwt_enabled: z.boolean(),
    supabase_url: z.string().nullable().default(null),
    supabase_anon_key: z.string().nullable().default(null),
    // Realtime für Listen-Projektionen (#1618): nur Invalidierungssignal.
    realtime_enabled: z.boolean().default(false),
  })
  .strict()

export type AuthConfigResponse = z.infer<typeof AuthConfigResponseSchema>
