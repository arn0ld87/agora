import { describe, expect, it } from 'vitest'
import {
  EmbeddingConfigurationSchema,
  EmbeddingConfigurationStatusSchema,
  EmbeddingMigrationJobSchema,
  EmbeddingMigrationProgressSchema,
  EmbeddingMigrationStatusSchema,
  EmbeddingIndexStatusSchema,
  EmbeddingProviderKindSchema,
  EmbeddingConfigurationScopeSchema,
} from '../embeddingContract'

describe('embeddingContract — Zod-Spiegel der Backend-Contracts', () => {
  it('akzeptiert alle 6 EmbeddingProviderKind-Werte', () => {
    for (const kind of [
      'ollama',
      'openai',
      'google',
      'custom',
      'ollama_cloud',
      'openai_compatible',
    ]) {
      expect(EmbeddingProviderKindSchema.parse(kind)).toBe(kind)
    }
  })

  it('lehnt anthropic und opencode_go als Embedding-Provider ab', () => {
    expect(() => EmbeddingProviderKindSchema.parse('anthropic')).toThrow()
    expect(() => EmbeddingProviderKindSchema.parse('opencode_go')).toThrow()
  })

  it('akzeptiert alle 7 EmbeddingConfigurationStatus-Werte', () => {
    for (const status of [
      'proposed',
      'probed',
      'reembedding',
      'validated',
      'active',
      'rolled_back',
      'failed',
    ]) {
      expect(EmbeddingConfigurationStatusSchema.parse(status)).toBe(status)
    }
  })

  it('akzeptiert alle 6 EmbeddingMigrationStatus-Werte', () => {
    for (const status of [
      'pending',
      'running',
      'validating',
      'completed',
      'rolled_back',
      'failed',
    ]) {
      expect(EmbeddingMigrationStatusSchema.parse(status)).toBe(status)
    }
  })

  it('akzeptiert alle 4 EmbeddingIndexStatus-Werte', () => {
    for (const status of [
      'active',
      'superseded',
      'rolled_back',
      'retired',
    ]) {
      expect(EmbeddingIndexStatusSchema.parse(status)).toBe(status)
    }
  })

  it('EmbeddingConfiguration: scope=project erfordert project_id', () => {
    const base = {
      id: 'emb-1',
      provider_connection_id: 'conn-1',
      provider_kind: 'ollama' as const,
      model_id: 'nomic-embed-text',
      dimensions: 768,
      index_version: 1,
      status: 'proposed' as const,
      created_at: '2026-07-12T12:00:00+00:00',
      updated_at: '2026-07-12T12:00:00+00:00',
    }
    expect(() =>
      EmbeddingConfigurationSchema.parse({ ...base, scope: 'project', project_id: null }),
    ).toThrow(/project_id/)
  })

  it('EmbeddingConfiguration: scope=global verbietet project_id', () => {
    const base = {
      id: 'emb-1',
      provider_connection_id: 'conn-1',
      provider_kind: 'ollama' as const,
      model_id: 'nomic-embed-text',
      dimensions: 768,
      index_version: 1,
      status: 'proposed' as const,
      created_at: '2026-07-12T12:00:00+00:00',
      updated_at: '2026-07-12T12:00:00+00:00',
    }
    expect(() =>
      EmbeddingConfigurationSchema.parse({ ...base, scope: 'global', project_id: 'proj-1' }),
    ).toThrow(/project_id/)
  })

  it('EmbeddingMigrationJob: source_index_version=0 nur mit target=1', () => {
    const base = {
      id: 'job-1',
      configuration_id: 'emb-1',
      target_index_version: 1,
      status: 'pending' as const,
      progress: {
        total: 0,
        processed: 0,
        failed: 0,
        started_at: null,
        finished_at: null,
      },
      error_message: null,
      created_at: '2026-07-12T12:00:00+00:00',
      updated_at: '2026-07-12T12:00:00+00:00',
    }
    expect(() =>
      EmbeddingMigrationJobSchema.parse({ ...base, source_index_version: 0 }),
    ).not.toThrow()
    expect(() =>
      EmbeddingMigrationJobSchema.parse({ ...base, source_index_version: 0, target_index_version: 2 }),
    ).toThrow(/Cold-Start|target=1/)
  })

  it('EmbeddingMigrationJob: source_index_version muss kleiner als target sein', () => {
    const base = {
      id: 'job-1',
      configuration_id: 'emb-1',
      target_index_version: 3,
      status: 'pending' as const,
      progress: {
        total: 0,
        processed: 0,
        failed: 0,
        started_at: null,
        finished_at: null,
      },
      error_message: null,
      created_at: '2026-07-12T12:00:00+00:00',
      updated_at: '2026-07-12T12:00:00+00:00',
    }
    expect(() =>
      EmbeddingMigrationJobSchema.parse({ ...base, source_index_version: 3 }),
    ).toThrow()
    expect(() =>
      EmbeddingMigrationJobSchema.parse({ ...base, source_index_version: 4 }),
    ).toThrow()
  })

  it('EmbeddingMigrationProgress: finished_at erfordert started_at', () => {
    expect(() =>
      EmbeddingMigrationProgressSchema.parse({
        total: 10,
        processed: 10,
        failed: 0,
        started_at: null,
        finished_at: '2026-07-12T12:00:00+00:00',
      }),
    ).toThrow(/started_at/)
  })

  it('EmbeddingMigrationProgress: finished_at darf nicht vor started_at sein', () => {
    expect(() =>
      EmbeddingMigrationProgressSchema.parse({
        total: 10,
        processed: 10,
        failed: 0,
        started_at: '2026-07-12T12:00:00+00:00',
        finished_at: '2026-07-12T11:00:00+00:00',
      }),
    ).toThrow(/finished_at/)
  })

  it('EmbeddingMigrationProgress: last_processed_id defaultet auf null (Legacy-Payloads)', () => {
    const parsed = EmbeddingMigrationProgressSchema.parse({
      total: 5,
      processed: 5,
      failed: 0,
      started_at: null,
      finished_at: null,
    })
    expect(parsed.last_processed_id).toBeNull()
  })

  it('EmbeddingMigrationProgress: last_processed_id wird als Resume-Cursor durchgereicht', () => {
    const parsed = EmbeddingMigrationProgressSchema.parse({
      total: 10,
      processed: 4,
      failed: 1,
      last_processed_id: 'uuid-003',
      started_at: '2026-07-13T08:00:00+00:00',
      finished_at: null,
    })
    expect(parsed.last_processed_id).toBe('uuid-003')
  })

  it('EmbeddingMigrationProgress: phase defaultet auf entity (Slice 4.4, Legacy-Payloads)', () => {
    const parsed = EmbeddingMigrationProgressSchema.parse({
      total: 5,
      processed: 5,
      failed: 0,
      started_at: null,
      finished_at: null,
    })
    expect(parsed.phase).toBe('entity')
  })

  it('EmbeddingMigrationProgress: phase wird als Cursor-Disambiguator durchgereicht', () => {
    for (const phase of ['entity', 'fact'] as const) {
      const parsed = EmbeddingMigrationProgressSchema.parse({
        total: 10,
        processed: 4,
        failed: 0,
        last_processed_id: 'rel-003',
        phase,
        started_at: '2026-07-13T08:00:00+00:00',
        finished_at: null,
      })
      expect(parsed.phase).toBe(phase)
    }
  })

  it('EmbeddingMigrationProgress: unbekannte phase wird abgelehnt', () => {
    expect(() =>
      EmbeddingMigrationProgressSchema.parse({
        total: 0,
        processed: 0,
        failed: 0,
        phase: 'relationship',
        started_at: null,
        finished_at: null,
      }),
    ).toThrow()
  })

  it('EmbeddingConfigurationScope akzeptiert nur global oder project', () => {
    expect(() => EmbeddingConfigurationScopeSchema.parse('team')).toThrow()
  })
})
