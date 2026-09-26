import { describe, expect, it } from 'vitest'

import manifestInputsJsonSchema from '../../../../schemas/manifest-inputs.schema.json'
import manifestSeedsJsonSchema from '../../../../schemas/manifest-seeds.schema.json'
import runManifestJsonSchema from '../../../../schemas/run-manifest.schema.json'
import stageRouteJsonSchema from '../../../../schemas/stage-route.schema.json'

import {
  AiRouteSnapshotSchema,
  ManifestDeviationSchema,
  ManifestInputsSchema,
  ManifestSeedsSchema,
  ManifestSimulationParamsSchema,
  RunManifestSchema,
  StageRouteSchema,
} from '../runManifestContract'

describe('run manifest contract (Issue #1274)', () => {
  it('keeps Zod top-level fields aligned with generated Pydantic schemas', () => {
    expect(Object.keys(RunManifestSchema.shape).sort()).toEqual(
      Object.keys(runManifestJsonSchema.properties).sort(),
    )
    expect(Object.keys(ManifestInputsSchema.shape).sort()).toEqual(
      Object.keys(manifestInputsJsonSchema.properties).sort(),
    )
    expect(Object.keys(ManifestSeedsSchema.shape).sort()).toEqual(
      Object.keys(manifestSeedsJsonSchema.properties).sort(),
    )
    expect(Object.keys(StageRouteSchema.shape).sort()).toEqual(
      Object.keys(stageRouteJsonSchema.properties).sort(),
    )
  })

  const minimalManifest = {
    schema_version: 1 as const,
    run_id: 'run_abc123',
    captured_at: '2026-08-12T10:00:00Z',
    inputs: {
      simulation_config_hash: 'sha256:def',
      graph_id: 'graph_001',
    },
    versions: { agora_version: '0.9.5', schema_version: '1.0.0' },
    routing: { stages: {} },
    prompts: { entries: {} },
    seeds: {},
    status: 'draft' as const,
  }

  it('parses a manifest without seed_document_hash/filename (Punkt 6: null statt "unknown")', () => {
    const result = RunManifestSchema.safeParse(minimalManifest)
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.inputs.seed_document_hash ?? null).toBeNull()
      expect(result.data.seeds.random_seed ?? null).toBeNull()
      expect(result.data.simulation ?? null).toBeNull()
      expect(result.data.deviations).toEqual([])
    }
  })

  it('stays backward-compatible with a manifest that predates simulation/deviations', () => {
    // Ein vor Issue #1274 geschriebenes Manifest kennt "simulation" und
    // "deviations" nicht — .strict() darf das nicht ablehnen.
    const legacyShape = { ...minimalManifest }
    const result = RunManifestSchema.safeParse(legacyShape)
    expect(result.success).toBe(true)
  })

  it('rejects unknown fields on AiRouteSnapshot (kein interner Transportkanal darf durchsickern)', () => {
    const result = AiRouteSnapshotSchema.safeParse({
      source: 'workspace',
      validated_capabilities: {},
    })
    expect(result.success).toBe(false)
  })

  it('accepts a strict AiRouteSnapshot with resolved legacy fields', () => {
    const result = AiRouteSnapshotSchema.safeParse({
      provider_connection_id: 'conn-a',
      model_id: 'gpt-4o',
      source: 'runtime',
      temperature: 0.5,
      max_tokens: 512,
      reasoning_effort: 'medium',
      provider_options: {},
    })
    expect(result.success).toBe(true)
  })

  it('allows StageRoute.base_url to be missing (Punkt 4: Legacy-Rekonstruktion ohne base_url)', () => {
    const result = StageRouteSchema.safeParse({ model: 'gemini-2.5-flash', provider: 'google' })
    expect(result.success).toBe(true)
  })

  it('requires platform and enable_graph_memory_update on ManifestSimulationParams', () => {
    expect(
      ManifestSimulationParamsSchema.safeParse({ platform: 'twitter', enable_graph_memory_update: true })
        .success,
    ).toBe(true)
    expect(ManifestSimulationParamsSchema.safeParse({ platform: 'twitter' }).success).toBe(false)
  })

  it('records field/original/replay on ManifestDeviation', () => {
    const result = ManifestDeviationSchema.safeParse({
      field: 'model_id',
      original: 'gpt-4o',
      replay: 'gemini-2.5-pro',
    })
    expect(result.success).toBe(true)
  })
})
