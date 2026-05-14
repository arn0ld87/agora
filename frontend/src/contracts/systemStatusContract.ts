/**
 * System-Status-Contract — Zod-Spiegel zu /api/status.
 *
 * Backend: backend/app/api/status.py::get_status
 * passthrough() auf allen Unterobjekten, damit Backend additive Felder
 * (z. B. neue gpu/disk-Subkeys) liefern darf ohne Frontend-Drift-Alarm.
 */
import { z } from 'zod'

export const SystemStatusBackendSchema = z
  .object({
    ok: z.boolean(),
    version: z.string().optional(),
    auth_mode: z.string().optional(),
  })
  .passthrough()

export const SystemStatusNeo4jSchema = z
  .object({
    reachable: z.boolean(),
    error: z.string().nullable().optional(),
    uri: z.string().optional(),
    is_connected: z.boolean().optional(),
    last_success_ts: z.string().nullable().optional(),
  })
  .passthrough()

export const SystemStatusOllamaSchema = z
  .object({
    reachable: z.boolean(),
    base_url: z.string().optional(),
    models_available: z.array(z.string()).default(() => []),
    default_model: z.string().nullable().optional(),
    error: z.string().nullable().optional(),
  })
  .passthrough()

export const SystemStatusDiskSchema = z
  .object({
    uploads: z
      .object({
        path: z.string().optional(),
        total_bytes: z.number().nullable().optional(),
        free_bytes: z.number().nullable().optional(),
        used_pct: z.number().nullable().optional(),
        error: z.string().optional(),
      })
      .passthrough(),
  })
  .passthrough()

export const SystemStatusGpuSchema = z
  .object({
    nvidia_smi_available: z.boolean().optional(),
    ollama_uses_gpu: z.boolean().nullable().optional(),
    hints: z.array(z.string()).optional(),
  })
  .passthrough()

export const SystemStatusResponseSchema = z
  .object({
    backend: SystemStatusBackendSchema,
    neo4j: SystemStatusNeo4jSchema,
    ollama: SystemStatusOllamaSchema,
    disk: SystemStatusDiskSchema,
    gpu: SystemStatusGpuSchema.optional(),
    timestamp: z.string(),
  })
  .passthrough()

export type SystemStatusResponse = z.infer<typeof SystemStatusResponseSchema>
