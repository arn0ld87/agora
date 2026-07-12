/**
 * Zod-Spiegel der Embedding-Verträge aus
 * backend/app/contracts/embedding_contract.py.
 *
 * Strikt defensiv: ``.strict()`` plus ``.passthrough()`` wo noetig,
 * damit Schema-Drift vom Backend frueh erkannt wird (Frontend-Zod
 * muss Backend-Schema spiegeln — siehe CI-Gate).
 */
import { z } from 'zod'

// ----------------------------------------------------------------------
// Provider-Restriktion (Sub-Literal der ProviderConnectionKind)
// ----------------------------------------------------------------------

export const EmbeddingProviderKindSchema = z.enum([
  'ollama',
  'openai',
  'google',
  'custom',
  'ollama_cloud',
  'openai_compatible',
])
export type EmbeddingProviderKind = z.infer<typeof EmbeddingProviderKindSchema>

export const EmbeddingConfigurationStatusSchema = z.enum([
  'proposed',
  'probed',
  'reembedding',
  'validated',
  'active',
  'rolled_back',
  'failed',
])
export type EmbeddingConfigurationStatus = z.infer<
  typeof EmbeddingConfigurationStatusSchema
>

export const EmbeddingConfigurationScopeSchema = z.enum(['global', 'project'])
export type EmbeddingConfigurationScope = z.infer<
  typeof EmbeddingConfigurationScopeSchema
>

export const EmbeddingMigrationStatusSchema = z.enum([
  'pending',
  'running',
  'validating',
  'completed',
  'rolled_back',
  'failed',
])
export type EmbeddingMigrationStatus = z.infer<
  typeof EmbeddingMigrationStatusSchema
>

export const EmbeddingIndexStatusSchema = z.enum([
  'active',
  'superseded',
  'rolled_back',
  'retired',
])
export type EmbeddingIndexStatus = z.infer<typeof EmbeddingIndexStatusSchema>

// ----------------------------------------------------------------------
// EmbeddingModelMetadata
// ----------------------------------------------------------------------

export const EmbeddingModelMetadataSchema = z
  .object({
    provider_kind: EmbeddingProviderKindSchema,
    model_id: z.string().min(1),
    display_name: z.string().min(1),
    embedding_dimensions: z.number().int().positive(),
    source: z.enum(['live', 'cached', 'fallback', 'custom']),
    deprecated: z.boolean().default(false),
    metadata_updated_at: z.string().datetime({ offset: true }).nullable().default(null),
  })
  .strict()
export type EmbeddingModelMetadata = z.infer<typeof EmbeddingModelMetadataSchema>

// ----------------------------------------------------------------------
// EmbeddingConfiguration
// ----------------------------------------------------------------------

const NullableDateTimeSchema = z
  .string()
  .datetime({ offset: true })
  .nullable()
  .default(null)

export const EmbeddingConfigurationSchema = z
  .object({
    id: z.string().min(1),
    provider_connection_id: z.string().min(1),
    provider_kind: EmbeddingProviderKindSchema,
    model_id: z.string().min(1),
    dimensions: z.number().int().positive(),
    scope: EmbeddingConfigurationScopeSchema,
    project_id: z.string().min(1).nullable().default(null),
    index_version: z.number().int().min(1),
    status: EmbeddingConfigurationStatusSchema,
    status_message: z.string().nullable().default(null),
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
    last_validated_at: NullableDateTimeSchema,
  })
  .strict()
  .superRefine((value, ctx) => {
    if (value.scope === 'project' && !value.project_id) {
      ctx.addIssue({
        code: 'custom',
        path: ['project_id'],
        message: 'project_id is required when scope="project"',
      })
    }
    if (value.scope === 'global' && value.project_id !== null) {
      ctx.addIssue({
        code: 'custom',
        path: ['project_id'],
        message: 'project_id must be null when scope="global"',
      })
    }
  })
export type EmbeddingConfiguration = z.infer<typeof EmbeddingConfigurationSchema>

export const EmbeddingConfigurationUpsertRequestSchema = z
  .object({
    provider_connection_id: z.string().min(1),
    provider_kind: EmbeddingProviderKindSchema,
    model_id: z.string().min(1),
    dimensions: z.number().int().positive(),
    scope: EmbeddingConfigurationScopeSchema,
    project_id: z.string().min(1).nullable().default(null),
  })
  .strict()
  .superRefine((value, ctx) => {
    if (value.scope === 'project' && !value.project_id) {
      ctx.addIssue({
        code: 'custom',
        path: ['project_id'],
        message: 'project_id is required when scope="project"',
      })
    }
    if (value.scope === 'global' && value.project_id !== null) {
      ctx.addIssue({
        code: 'custom',
        path: ['project_id'],
        message: 'project_id must be null when scope="global"',
      })
    }
  })
export type EmbeddingConfigurationUpsertRequest = z.infer<
  typeof EmbeddingConfigurationUpsertRequestSchema
>

export const EmbeddingConfigurationResponseSchema = z
  .object({
    configuration: EmbeddingConfigurationSchema,
  })
  .strict()
export type EmbeddingConfigurationResponse = z.infer<
  typeof EmbeddingConfigurationResponseSchema
>

export const EmbeddingConfigurationsListResponseSchema = z
  .object({
    configurations: z.array(EmbeddingConfigurationSchema),
  })
  .strict()
export type EmbeddingConfigurationsListResponse = z.infer<
  typeof EmbeddingConfigurationsListResponseSchema
>

// ----------------------------------------------------------------------
// EmbeddingMigrationJob
// ----------------------------------------------------------------------

export const EmbeddingMigrationProgressSchema = z
  .object({
    total: z.number().int().min(0),
    processed: z.number().int().min(0),
    failed: z.number().int().min(0),
    started_at: NullableDateTimeSchema,
    finished_at: NullableDateTimeSchema,
  })
  .strict()
  .superRefine((value, ctx) => {
    if (value.finished_at && !value.started_at) {
      ctx.addIssue({
        code: 'custom',
        path: ['started_at'],
        message: 'started_at must be set if finished_at is set',
      })
    }
    if (
      value.started_at &&
      value.finished_at &&
      new Date(value.finished_at) < new Date(value.started_at)
    ) {
      ctx.addIssue({
        code: 'custom',
        path: ['finished_at'],
        message: 'finished_at cannot be before started_at',
      });
    }
  })
export type EmbeddingMigrationProgress = z.infer<
  typeof EmbeddingMigrationProgressSchema
>

export const EmbeddingMigrationJobSchema = z
  .object({
    id: z.string().min(1),
    configuration_id: z.string().min(1),
    source_index_version: z.number().int().min(0), // 0 = Cold-Start-Sentinel
    target_index_version: z.number().int().min(1),
    status: EmbeddingMigrationStatusSchema,
    progress: EmbeddingMigrationProgressSchema,
    error_message: z.string().nullable().default(null),
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
  })
  .strict()
  .superRefine((value, ctx) => {
    if (value.source_index_version === 0 && value.target_index_version !== 1) {
      ctx.addIssue({
        code: 'custom',
        path: ['source_index_version'],
        message: 'Cold-Start-Sentinel: source_index_version=0 ist nur fuer target=1 zulaessig',
      });
    }
    if (
      value.source_index_version > 0 &&
      value.source_index_version >= value.target_index_version
    ) {
      ctx.addIssue({
        code: 'custom',
        path: ['source_index_version'],
        message: 'source_index_version muss kleiner als target_index_version sein',
      });
    }
  })
export type EmbeddingMigrationJob = z.infer<typeof EmbeddingMigrationJobSchema>

export const EmbeddingMigrationJobResponseSchema = z
  .object({
    job: EmbeddingMigrationJobSchema,
  })
  .strict()
export type EmbeddingMigrationJobResponse = z.infer<
  typeof EmbeddingMigrationJobResponseSchema
>

export const EmbeddingMigrationJobsListResponseSchema = z
  .object({
    jobs: z.array(EmbeddingMigrationJobSchema),
  })
  .strict()
export type EmbeddingMigrationJobsListResponse = z.infer<
  typeof EmbeddingMigrationJobsListResponseSchema
>

// ----------------------------------------------------------------------
// EmbeddingIndexVersion
// ----------------------------------------------------------------------

export const EmbeddingIndexVersionSchema = z
  .object({
    version: z.number().int().min(1),
    provider_connection_id: z.string().min(1),
    model_id: z.string().min(1),
    dimensions: z.number().int().positive(),
    index_name: z.string().min(1),
    property_key: z.string().min(1),
    status: EmbeddingIndexStatusSchema,
    created_at: z.string().datetime({ offset: true }),
    retired_at: NullableDateTimeSchema,
  })
  .strict()
  .superRefine((value, ctx) => {
    if (value.status === 'retired' && !value.retired_at) {
      ctx.addIssue({
        code: 'custom',
        path: ['retired_at'],
        message: 'retired_at is required when status="retired"',
      });
    }
    if (value.status !== 'retired' && value.retired_at) {
      ctx.addIssue({
        code: 'custom',
        path: ['retired_at'],
        message: 'retired_at must be null when status is not "retired"',
      });
    }
  })
export type EmbeddingIndexVersion = z.infer<typeof EmbeddingIndexVersionSchema>

// ----------------------------------------------------------------------
// Ollama-Pull-Report
// ----------------------------------------------------------------------

export const OllamaPullReportSchema = z
  .object({
    model: z.string().min(1),
    status: z.enum(['success', 'error']),
    digest: z.string().nullable().default(null),
    total_bytes: z.number().int().min(0),
    completed_bytes: z.number().int().min(0),
    error_message: z.string().nullable().default(null),
    layers_downloaded: z.number().int().min(0),
  })
  .strict()
export type OllamaPullReport = z.infer<typeof OllamaPullReportSchema>

export const OllamaPullReportResponseSchema = z
  .object({
    report: OllamaPullReportSchema,
  })
  .strict()
export type OllamaPullReportResponse = z.infer<
  typeof OllamaPullReportResponseSchema
>
