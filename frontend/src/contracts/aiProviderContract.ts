/** Canonical Zod mirror of backend/app/contracts/ai_provider_contract.py. */
import { z } from 'zod'

export const CapabilityStateSchema = z.enum(['supported', 'unsupported', 'unknown'])
export type CapabilityState = z.infer<typeof CapabilityStateSchema>

const UNKNOWN_MODEL_CAPABILITIES = {
  chat: 'unknown',
  embeddings: 'unknown',
  streaming: 'unknown',
  tool_calling: 'unknown',
  json_object: 'unknown',
  json_schema: 'unknown',
  vision: 'unknown',
  reasoning: 'unknown',
} as const

export const ModelCapabilitiesSchema = z.object({
  chat: CapabilityStateSchema.default('unknown'),
  embeddings: CapabilityStateSchema.default('unknown'),
  streaming: CapabilityStateSchema.default('unknown'),
  tool_calling: CapabilityStateSchema.default('unknown'),
  json_object: CapabilityStateSchema.default('unknown'),
  json_schema: CapabilityStateSchema.default('unknown'),
  vision: CapabilityStateSchema.default('unknown'),
  reasoning: CapabilityStateSchema.default('unknown'),
}).strict()
export type ModelCapabilities = z.infer<typeof ModelCapabilitiesSchema>

// OpenCode Go remains a CLI bridge and is unsupported for provider connections
// in this slice.
const ProviderConnectionKindSchema = z.enum([
  'ollama',
  'openai',
  'google',
  'anthropic',
  'custom',
  'ollama_cloud',
  'openai_compatible',
  'minimax',
  'github_copilot',
  'cloud',
  'unknown',
])

const NullableDateTimeSchema = z.string().datetime({ offset: true }).nullable().default(null)

const PUBLIC_BASE_URL_PATTERN = /^https?:\/\/(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:.]+\])(?::[0-9]{1,5})?(?:\/[^\s?#]*)?$/

export const PublicBaseUrlSchema = z.string().regex(PUBLIC_BASE_URL_PATTERN).superRefine((value, context) => {
  try {
    const parsed = new URL(value)
    const hostname = parsed.hostname.replace(/^\[|\]$/g, '').toLowerCase()
    const isIpv4Private = /^10\./.test(hostname)
      || /^127(?:\.\d{1,3}){3}$/.test(hostname)
      || /^169\.254\./.test(hostname)
      || /^192\.168\./.test(hostname)
      || /^172\.(?:1[6-9]|2\d|3[0-1])\./.test(hostname)
    if (
      !['http:', 'https:'].includes(parsed.protocol) ||
      !parsed.hostname ||
      parsed.username ||
      parsed.password ||
      parsed.search ||
      parsed.hash ||
      ['localhost', '::1'].includes(hostname) ||
      isIpv4Private
    ) {
      context.addIssue({ code: 'custom', message: 'base_url must be a public HTTP(S) base URL' })
    }
  } catch {
    context.addIssue({ code: 'custom', message: 'base_url must be a public HTTP(S) base URL' })
  }
})

export const LocalOllamaBaseUrlSchema = z.string().superRefine((value, context) => {
  try {
    const parsed = new URL(value)
    const hostname = parsed.hostname.replace(/^\[|\]$/g, '').toLowerCase()
    const isIpv4Loopback = /^127(?:\.\d{1,3}){3}$/.test(hostname)
      && hostname.split('.').every((octet) => Number(octet) <= 255)
    if (
      !['http:', 'https:'].includes(parsed.protocol)
      || !parsed.hostname
      || parsed.username
      || parsed.password
      || parsed.search
      || parsed.hash
      || !(['localhost', '::1'].includes(hostname) || isIpv4Loopback)
    ) {
      context.addIssue({ code: 'custom', message: 'base_url must be a loopback HTTP(S) URL for local Ollama' })
    }
  } catch {
    context.addIssue({ code: 'custom', message: 'base_url must be a loopback HTTP(S) URL for local Ollama' })
  }
})

export const ProviderConnectionBaseSchema = z.object({
  id: z.string().min(1),
  provider_kind: ProviderConnectionKindSchema,
  display_name: z.string().min(1),
  transport: z.enum(['http', 'local']),
  auth_mode: z.enum(['none', 'api_key', 'oauth', 'session']),
  base_url: z.union([PublicBaseUrlSchema, LocalOllamaBaseUrlSchema]).nullable().default(null),
  enabled: z.boolean().default(true),
  status: z.enum(['unknown', 'connected', 'degraded', 'disconnected', 'error']).default('unknown'),
  status_message: z.string().nullable().default(null),
  secret_ref: z.string().nullable().default(null),
  capabilities: z.record(z.string(), CapabilityStateSchema).default({}),
  created_at: NullableDateTimeSchema,
  updated_at: NullableDateTimeSchema,
  last_tested_at: NullableDateTimeSchema,
}).strict()

export const ProviderConnectionSchema = ProviderConnectionBaseSchema.superRefine((value, context) => {
  if (value.base_url === null) return
  const baseUrlSchema = value.provider_kind === 'ollama'
    ? LocalOllamaBaseUrlSchema
    : PublicBaseUrlSchema
  const result = baseUrlSchema.safeParse(value.base_url)
  if (!result.success) {
    context.addIssue({ code: 'custom', path: ['base_url'], message: result.error.issues[0]?.message ?? 'invalid base_url' })
  }
})
export type ProviderConnection = z.infer<typeof ProviderConnectionSchema>

export const ProviderConnectionUpsertRequestSchema = z.object({
  display_name: z.string().min(1),
  provider_kind: ProviderConnectionKindSchema,
  base_url: z.string().nullable().default(null),
  enabled: z.boolean().default(true),
  api_key: z.string().nullable().default(null),
}).strict().superRefine((value, context) => {
  if (value.base_url === null) return
  const baseUrlSchema = value.provider_kind === 'ollama'
    ? LocalOllamaBaseUrlSchema
    : PublicBaseUrlSchema
  const result = baseUrlSchema.safeParse(value.base_url)
  if (!result.success) {
    context.addIssue({ code: 'custom', path: ['base_url'], message: result.error.issues[0]?.message ?? 'invalid base_url' })
  }
})
export type ProviderConnectionUpsertRequest = z.infer<typeof ProviderConnectionUpsertRequestSchema>

export const ProviderConnectionResponseSchema = z.object({
  connection: ProviderConnectionSchema,
}).strict()
export type ProviderConnectionResponse = z.infer<typeof ProviderConnectionResponseSchema>

export const ProviderConnectionsListResponseSchema = z.object({
  items: z.array(ProviderConnectionSchema),
  total: z.number().int().nonnegative(),
}).strict()
export type ProviderConnectionsListResponse = z.infer<typeof ProviderConnectionsListResponseSchema>

// Mirrors backend ProviderProbeStatus (services/provider_connections/adapters.py).
// Distinct from ProviderConnection.status: this is the raw, per-probe result
// before the service maps it onto the persisted connection status.
export const ProviderProbeStatusSchema = z.enum([
  'available',
  'unavailable',
  'invalid_credentials',
  'degraded',
  'unsupported',
])
export type ProviderProbeStatus = z.infer<typeof ProviderProbeStatusSchema>

export const ProviderConnectionTestResultSchema = z.object({
  status: ProviderProbeStatusSchema,
  status_message: z.string().nullable().default(null),
  models_found: z.number().int().nonnegative(),
}).strict()
export type ProviderConnectionTestResult = z.infer<typeof ProviderConnectionTestResultSchema>

export const AiModelSchema = z.object({
  provider_connection_id: z.string().min(1),
  model_id: z.string().min(1),
  display_name: z.string().min(1),
  capabilities: ModelCapabilitiesSchema.default(UNKNOWN_MODEL_CAPABILITIES),
  source: z.enum(['live', 'cached', 'fallback', 'custom']),
  status: z.enum(['unknown', 'available', 'unavailable', 'deprecated']).default('unknown'),
  context_window: z.number().int().positive().nullable().default(null),
  max_output_tokens: z.number().int().positive().nullable().default(null),
  embedding_dimensions: z.number().int().positive().nullable().default(null),
  local_or_cloud: z.enum(['local', 'cloud', 'unknown']).default('unknown'),
  deprecated: z.boolean().default(false),
  metadata_updated_at: NullableDateTimeSchema,
}).strict()
export type AiModel = z.infer<typeof AiModelSchema>

const StageIdSchema = z.enum([
  'document_ingest',
  'ontology_generation',
  'graph_build',
  'persona_generation',
  'simulation_rounds',
  'report_generation',
  'evaluation',
])

const LegacyStageRouteOptionsSchema = z.object({
  temperature: z.number().nullable(),
  max_tokens: z.number().int().nullable(),
  reasoning_effort: z.enum(['none', 'minimal', 'low', 'medium', 'high']).nullable(),
  had_reserved_value: z.boolean(),
  reserved_value: z.null(),
}).strict()

export const AiProviderOptionsSchema = z.object({
  base_url: PublicBaseUrlSchema.nullable().optional(),
  num_ctx: z.number().int().positive().optional(),
  __legacy_stage_route__: LegacyStageRouteOptionsSchema.optional(),
}).strict()
export type AiProviderOptions = z.infer<typeof AiProviderOptionsSchema>

export const RouteSourceSchema = z.enum([
  'default',
  'profile',
  'stage_override',
  'run_override',
  'project',
  'workspace',
  'provider_fallback',
  'runtime',
  'legacy',
])
export type RouteSource = z.infer<typeof RouteSourceSchema>

export const AiRouteSchema = z.object({
  stage: StageIdSchema.nullable().default(null),
  provider_connection_id: z.string().nullable().default(null),
  model_id: z.string().nullable().default(null),
  source: RouteSourceSchema,
  validated_capabilities: z.record(z.string(), CapabilityStateSchema).default({}),
  provider_options: AiProviderOptionsSchema.default({}),
  resolved_at: NullableDateTimeSchema,
  fallback_reason: z.string().nullable().default(null),
}).strict().superRefine((route, context) => {
  if (route.source === 'provider_fallback' && !route.fallback_reason?.trim()) {
    context.addIssue({
      code: 'custom',
      message: 'provider_fallback requires a non-blank fallback_reason',
      path: ['fallback_reason'],
    })
  }
})
export type AiRoute = z.infer<typeof AiRouteSchema>
