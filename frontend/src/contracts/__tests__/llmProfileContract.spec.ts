import { describe, expect, it } from 'vitest'

import llmProfileJsonSchema from '../../../../schemas/llm-profile.schema.json'

import { LlmProfileSchema, LlmProviderSchema } from '../llmProfileContract'

/**
 * Issue #1282 — das Frontend ``LlmProviderSchema`` muss jedes Provider-Token
 * akzeptieren, das das Backend in ``LlmProfile.provider`` (``ProviderType``)
 * emitieren kann. Der Slice #1282 hat ``bedrock`` zu ``ProviderType`` hinzugefügt,
 * aber die Zod-Spiegel in ``llmProfileContract.ts`` wurde zunächst nicht
 * nachgezogen — der Zod-Mirror-CI hat das nicht abgefangen, weil für diesen
 * Contract kein Spiegeltest existierte. Dieser Test schließt die Lücke: jedes
 * enum-Token aus ``schemas/llm-profile.schema.json`` muss unter
 * ``LlmProviderSchema`` parsen.
 */
describe('llmProfileContract mirrors backend LlmProfile', () => {
  const providerEnum = llmProfileJsonSchema.properties.provider.enum as string[]

  it('LlmProviderSchema accepts every provider token the backend can emit', () => {
    for (const token of providerEnum) {
      expect(LlmProviderSchema.safeParse(token).success).toBe(true)
    }
  })

  it('LlmProviderSchema includes bedrock (Issue #1282)', () => {
    expect(providerEnum).toContain('bedrock')
    expect(LlmProviderSchema.safeParse('bedrock').success).toBe(true)
  })

  it('a bedrock LlmProfile round-trips through LlmProfileSchema', () => {
    const bedrockProfile = {
      id: 'profile-bedrock',
      name: 'Bedrock Sonnet 5',
      provider: 'bedrock',
      base_url: 'https://bedrock-mantle.eu-central-1.api.aws/v1',
      model_name: 'anthropic.claude-sonnet-5',
      api_key: null,
      is_default: false,
      created_at: '2026-08-12T18:00:00Z',
      updated_at: '2026-08-12T18:00:00Z',
    }
    const parsed = LlmProfileSchema.safeParse(bedrockProfile)
    expect(parsed.success).toBe(true)
  })
})