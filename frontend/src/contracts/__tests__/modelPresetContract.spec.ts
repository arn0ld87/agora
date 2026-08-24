import { describe, expect, it } from 'vitest'

import modelPresetJsonSchema from '../../../../schemas/model-preset.schema.json'
import availableModelsJsonSchema from '../../../../schemas/available-models-response.schema.json'

import { AvailableModelsResponseSchema, ModelPresetSchema } from '../modelPresetContract'

/**
 * Issue #1395 — ``ModelPreset``/``AvailableModelsResponse`` waren bis dahin
 * handgeschriebene TS-Interfaces ohne Gegenstueck in ``schemas/*.json`` und
 * ohne Zod-Drift-Check (CodeRabbit-P1-Finding auf PR #1390). Dieser Test
 * schliesst die Luecke: jeder Feldname aus dem generierten JSON-Schema muss
 * im Zod-Spiegel vorkommen, und typische Backend-Payloads muessen strikt
 * parsen.
 */
describe('modelPresetContract mirrors backend model_preset_contract', () => {
  it('ModelPresetSchema declares exactly the fields of model-preset.schema.json', () => {
    const backendFields = Object.keys(modelPresetJsonSchema.properties).sort()
    const zodFields = Object.keys(ModelPresetSchema.shape).sort()
    expect(zodFields).toEqual(backendFields)
  })

  it('AvailableModelsResponseSchema declares exactly the fields of available-models-response.schema.json', () => {
    const backendFields = Object.keys(availableModelsJsonSchema.properties).sort()
    const zodFields = Object.keys(AvailableModelsResponseSchema.shape).sort()
    expect(zodFields).toEqual(backendFields)
  })

  it('parses a curated preset (label_key, no legacy label)', () => {
    const preset = {
      name: 'qwen3-coder-next:cloud',
      label_key: 'llm.preset.cloud.qwen3_coder_next',
      kind: 'cloud',
    }
    expect(ModelPresetSchema.safeParse(preset).success).toBe(true)
  })

  it('parses an Ollama-tag preset (legacy label, no label_key)', () => {
    const preset = {
      name: 'qwen2.5:32b',
      label: 'qwen2.5:32b',
      size: 19851349248,
      family: 'qwen2',
      parameter_size: '32.8B',
      kind: 'ollama',
    }
    expect(ModelPresetSchema.safeParse(preset).success).toBe(true)
  })

  it('rejects an unknown field on ModelPreset (strict)', () => {
    const preset = { name: 'x', unexpected_field: true }
    expect(ModelPresetSchema.safeParse(preset).success).toBe(false)
  })

  it('parses a full available-models response', () => {
    const response = {
      ollama: [],
      presets: [
        {
          name: 'zai.glm-4.7-flash',
          label_key: 'llm.preset.bedrock.glm_4_7_flash',
          kind: 'bedrock',
        },
      ],
      current_default: 'qwen3-coder-next:cloud',
      default_provider: 'bedrock',
      ollama_base_url: null,
      ollama_reachable: false,
      ollama_error: null,
      ollama_skipped: true,
      ollama_skipped_provider: 'bedrock',
      ollama_skip_reason: 'Active provider is bedrock',
      neo4j_reachable: true,
      neo4j_error: null,
      neo4j_uri: 'bolt://localhost:7687',
      default_language: 'de',
      agent_tools_enabled: false,
      max_tool_calls_per_action: 2,
    }
    const parsed = AvailableModelsResponseSchema.safeParse(response)
    expect(parsed.success).toBe(true)
  })
})
