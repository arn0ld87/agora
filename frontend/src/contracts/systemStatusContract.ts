/**
 * System-Status-Contract — Zod-Spiegel zu /api/status.
 *
 * Backend: backend/app/api/status.py::get_status
 * passthrough() auf allen Unterobjekten, damit Backend additive Felder
 * (z. B. neue gpu/disk-Subkeys) liefern darf ohne Frontend-Drift-Alarm.
 */
import { z } from 'zod'

/**
 * Spiegel von `backend/app/contracts/system_status_contract.py::StatusCheckError`.
 *
 * Ersetzt seit #1458 den rohen `str(exc)`, der zuvor an drei Stellen
 * (neo4j, ollama, disk) direkt in die Antwort floss — ein Informationsleck
 * (Pfade, Hostnamen, Treiberdetails) und für die UI unrenderbarer
 * Traceback-Text. `code` ist bewusst `z.string()` statt eines Enums: ein
 * neuer Backend-Code darf den Zod-Parse nicht invalidieren, das Frontend
 * übersetzt ihn mit Fallback für unbekannte Werte
 * (`unreachable` | `timeout` | `auth` | `unexpected` sind die bekannten
 * Werte, siehe `StatusErrorCode` im Backend-Contract).
 */
export const StatusCheckErrorSchema = z
  .object({
    code: z.string(),
  })
  .passthrough()

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
    error: StatusCheckErrorSchema.nullable().optional(),
    uri: z.string().optional(),
    is_connected: z.boolean().optional(),
    last_success_ts: z.string().nullable().optional(),
  })
  .passthrough()

/**
 * Spiegel von `backend/app/contracts/system_status_contract.py::SystemStatusOllama`
 * (generiert nach `schemas/system-status-ollama.schema.json`).
 *
 * `reachable` ist dreiwertig: `true` erreichbar, `false` Probe fehlgeschlagen,
 * `null` Probe übersprungen — Letzteres ist KEIN Fehlerzustand und darf nicht
 * als "offline" gerendert werden.
 */
export const SystemStatusOllamaSchema = z
  .object({
    reachable: z.boolean().nullable(),
    skipped: z.boolean().optional(),
    // Maschinenlesbarer i18n-Schlüssel. `reason` ist reines Debug-Feld und
    // gehört nicht in die UI — es enthält englische Backend-Prosa.
    skipped_provider: z.string().nullable().optional(),
    reason: z.string().nullable().optional(),
    base_url: z.string().nullable().optional(),
    models_available: z.array(z.string()).default(() => []),
    default_model: z.string().nullable().optional(),
    // Strukturiert seit #1458 — vorher `z.string()` mit rohem Exception-Text.
    error: StatusCheckErrorSchema.nullable().optional(),
  })
  .passthrough()

/**
 * Spiegel von `backend/app/contracts/system_status_contract.py::SystemStatusE2E`
 * (generiert nach `schemas/system-status-e2e.schema.json`).
 *
 * Meldet, ob der Backend-Prozess im E2E-Stub-Modus läuft, also ob
 * `LLMClient.chat_json` Konservenantworten statt echter Provider-Antworten
 * liefert. `stub_active` ist genau dann `true`, wenn `llm_mode === 'stub'`.
 */
export const SystemStatusE2ESchema = z
  .object({
    llm_mode: z.string().nullable().optional(),
    stub_active: z.boolean(),
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
        // Strukturiert seit #1458 — vorher `z.string()` mit rohem Exception-Text.
        error: StatusCheckErrorSchema.optional(),
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
    // Optional, damit ein aelteres Backend ohne den Teilbaum nicht am
    // Zod-Parse scheitert. Der E2E-Helper assertiert die Anwesenheit selbst.
    e2e: SystemStatusE2ESchema.optional(),
    disk: SystemStatusDiskSchema,
    gpu: SystemStatusGpuSchema.optional(),
    timestamp: z.string(),
  })
  .passthrough()

export type SystemStatusResponse = z.infer<typeof SystemStatusResponseSchema>
