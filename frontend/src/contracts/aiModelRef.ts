/**
 * AiModelRef — kanonische Modell-Referenz fuer AiModelPicker und Run-Snapshots.
 *
 * Slice 5.0+5.1: TS-SSoT, noch keine Backend-Anbindung.
 * Backend-Spiegel kommt in Slice 5.3 als `AiRoute` in
 * `backend/app/contracts/ai_route_contract.py`.
 *
 * Eine AiModelRef identifiziert ein (Provider-Connection, Modell)-Paar
 * plus die Quelle der Auswahl. Sie ist bewusst klein gehalten — groessere
 * Metadaten (Capabilities, Status) bleiben in der ProviderConnection bzw.
 * im Model-Katalog und werden bei Bedarf nachgeschlagen.
 *
 * Master-Prompt §6.3: jede effektive Auswahl muss im Run-Snapshot und
 * Audit-Trail mit Provider, Modell, Quelle der Auswahl und Faehigkeiten
 * gespeichert werden. Diese Struktur deckt das ab.
 *
 * Slice 5.4: Zod-Spiegel (AiModelRefSchema, AiModelSourceSchema,
 * AiModelRefInputSchema) fuer localStorage-Validierung in HeroNewRun
 * und Adapter-Tests. Spiegel bewusst eng am TS-Interface — Capability-
 * Filter und Fallback-Reason bleiben optional.
 */
import { z } from 'zod'

export const AiModelSourceSchema = z.enum([
  'stage-override',
  'run-override',
  'project-default',
  'workspace-default',
  'explicit',
  'fallback',
])
export type AiModelSourceType = z.infer<typeof AiModelSourceSchema>

export const AiModelRefSchema = z.object({
  provider_connection_id: z.string().min(1),
  model_id: z.string().min(1),
  source: AiModelSourceSchema,
  capability_filter: z.string().optional(),
  fallback_reason: z.string().optional(),
}).strict()
export type AiModelRefValidated = z.infer<typeof AiModelRefSchema>

export const AiProviderKindSchema = z.enum([
  'ollama',
  'ollama_cloud',
  'openai',
  'anthropic',
  'gemini',
  'openai_compatible',
  'mock',
])

export const AiCapabilitySchema = z.enum([
  'chat',
  'embeddings',
  'streaming',
  'tool_calling',
  'json_object',
  'json_schema',
  'vision',
  'reasoning',
])

export const AiModelStatusSchema = z.enum([
  'available',
  'unavailable',
  'degraded',
  'unsupported',
  'invalid_credentials',
])

export const AiModelPickerModeSchema = z.enum(['chat', 'embedding'])

export const AiModelRefInputSchema = z.object({
  provider_connection_id: z.string().min(1),
  provider_kind: AiProviderKindSchema,
  display_name: z.string().min(1),
  model_id: z.string().min(1),
  context_window: z.number().int().positive().optional(),
  capabilities: z.array(AiCapabilitySchema),
  status: AiModelStatusSchema,
  is_workspace_default: z.boolean().optional(),
  local_or_cloud: z.enum(['local', 'cloud']),
  unsupported_capabilities: z.array(AiCapabilitySchema).optional(),
}).strict()
export type AiModelRefInputValidated = z.infer<typeof AiModelRefInputSchema>

export interface AiModelRef {
  /** Provider-Connection-ID (Slice 3). */
  readonly provider_connection_id: string
  /** Modell-Name innerhalb der Connection. */
  readonly model_id: string
  /** Quelle der Auswahl (Master-Prompt §6.3 Hierarchie). */
  readonly source: AiModelSource
  /** Optional: Capability-Filter, der bei der Auswahl aktiv war. */
  readonly capability_filter?: string
  /** Optional: Begruendung fuer Fallback (z.B. "Provider offline"). */
  readonly fallback_reason?: string
}

/** Quelle der Auswahl — gespiegelt mit Slice 5.3 Routing-Hierarchie. */
export type AiModelSource =
  | 'stage-override'
  | 'run-override'
  | 'project-default'
  | 'workspace-default'
  | 'explicit'
  | 'fallback'

/**
 * AiModelRefInput — was die Picker-Komponente als Input akzeptiert
 * (Mock-Daten-Format fuer Slice 5.1).
 *
 * Slice 5.2 ersetzt das durch `useAvailableModels()` mit Capability-
 * Filter, Live-Status, Provider-Group-Logik. Diese Struktur bleibt
 * aber der Daten-Vertrag fuer die Komponente.
 */
export interface AiModelRefInput {
  readonly provider_connection_id: string
  readonly provider_kind: AiProviderKind
  readonly display_name: string
  readonly model_id: string
  readonly context_window?: number
  readonly capabilities: readonly AiCapability[]
  readonly status: AiModelStatus
  readonly is_workspace_default?: boolean
  readonly local_or_cloud: 'local' | 'cloud'
  readonly unsupported_capabilities?: readonly AiCapability[]
}

export type AiProviderKind =
  | 'ollama'
  | 'ollama_cloud'
  | 'openai'
  | 'anthropic'
  | 'gemini'
  | 'openai_compatible'
  | 'mock'

export type AiCapability =
  | 'chat'
  | 'embeddings'
  | 'streaming'
  | 'tool_calling'
  | 'json_object'
  | 'json_schema'
  | 'vision'
  | 'reasoning'

export type AiModelStatus =
  | 'available'
  | 'unavailable'
  | 'degraded'
  | 'unsupported'
  | 'invalid_credentials'

/**
 * Mode der Picker-Komponente.
 * - `chat`: waehlt aus chat-faehigen Modellen.
 * - `embedding`: waehlt aus embedding-faehigen Modellen.
 * Slice 5.1 unterstuetzt beide; Capabilities werden je nach mode gefiltert.
 */
export type AiModelPickerMode = 'chat' | 'embedding'

/**
 * Stable String-ID fuer Combobox-Items. Komposition aus
 * `provider_connection_id` und `model_id`, getrennt durch `\u0000`,
 * damit sie nicht mit normalen User-Strings kollidieren kann.
 */
export function aiModelItemId(input: AiModelRefInput): string {
  return `${input.provider_connection_id}\u0000${input.model_id}`
}

export function parseAiModelItemId(id: string): {
  provider_connection_id: string
  model_id: string
} {
  const sep = id.indexOf('\u0000')
  if (sep < 0) {
    throw new Error(`Ungueltige AiModel-Item-ID: ${JSON.stringify(id)}`)
  }
  return {
    provider_connection_id: id.slice(0, sep),
    model_id: id.slice(sep + 1),
  }
}
