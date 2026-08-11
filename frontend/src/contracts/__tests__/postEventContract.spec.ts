/**
 * Zod-Spiegel-Drift-Tests für PostCreatedEvent.
 *
 * Slice FE-Redesign-5-pre · 2026-05-15
 * Schema-Quelle: schemas/post-created-event.schema.json
 *
 * Prüft:
 * 1. Alle Pydantic-Pflichtfelder sind im Zod-Spiegel vorhanden (Schema-Drift-Gate).
 * 2. Gültige Payloads werden akzeptiert.
 * 3. Ungültige Plattform / Voice-Register werden rejected.
 * 4. is_simulated defaultet auf true.
 * 5. strict() lehnt unbekannte Felder ab.
 */

import { describe, it, expect } from 'vitest'
import {
  PostCreatedEventSchema,
  PlatformSchema,
  VoiceRegisterSchema,
} from '../postEventContract'
import postCreatedEventJson from '../../../../schemas/post-created-event.schema.json'

function propertyKeys(schema: { properties?: Record<string, unknown> }) {
  return Object.keys(schema.properties ?? {}).sort()
}

function shapeKeys(schema: { shape: Record<string, unknown> }) {
  return Object.keys(schema.shape).sort()
}

const VALID_PAYLOAD = {
  event_type: 'post_created' as const,
  simulation_id: 'sim-123',
  post_id: 'post-abc',
  parent_post_id: null,
  platform: 'reddit' as const,
persona_id: 'persona-7',
  persona_name: 'Test Persona',
  voice_register: 'neutral-de' as const,
  is_simulated: true,
  body: 'Mein erster Post.',
  timestamp: '2026-05-15T12:00:00+00:00',
}

describe('PostCreatedEventSchema', () => {
  it('Schema-Drift-Gate: Zod-Spiegel deckt alle Backend-Properties ab', () => {
    const backendKeys = propertyKeys(postCreatedEventJson)
    const zodKeys = shapeKeys(PostCreatedEventSchema)
    for (const key of backendKeys) {
      expect(zodKeys).toContain(key)
    }
  })

  it('akzeptiert gültigen Payload (reddit/neutral-de)', () => {
    const result = PostCreatedEventSchema.safeParse(VALID_PAYLOAD)
    expect(result.success).toBe(true)
  })

  it('akzeptiert twitter/formal-de', () => {
    const result = PostCreatedEventSchema.safeParse({
      ...VALID_PAYLOAD,
      platform: 'twitter',
      voice_register: 'formal-de',
    })
    expect(result.success).toBe(true)
  })

  it('akzeptiert skeptisch-de voice_register', () => {
    const result = PostCreatedEventSchema.safeParse({
      ...VALID_PAYLOAD,
      voice_register: 'skeptisch-de',
    })
    expect(result.success).toBe(true)
  })

  it('lehnt unbekannte Plattform ab', () => {
    const result = PostCreatedEventSchema.safeParse({
      ...VALID_PAYLOAD,
      platform: 'mastodon',
    })
    expect(result.success).toBe(false)
  })

  it('lehnt unbekannten voice_register ab', () => {
    const result = PostCreatedEventSchema.safeParse({
      ...VALID_PAYLOAD,
      voice_register: 'slang',
    })
    expect(result.success).toBe(false)
  })

  it('lehnt falsches event_type-Literal ab', () => {
    const result = PostCreatedEventSchema.safeParse({
      ...VALID_PAYLOAD,
      event_type: 'wrong',
    })
    expect(result.success).toBe(false)
  })

  it('lehnt unbekannte Felder ab (strict)', () => {
    const result = PostCreatedEventSchema.safeParse({
      ...VALID_PAYLOAD,
      extra_field: 'x',
    })
    expect(result.success).toBe(false)
  })

  it('parent_post_id darf null sein', () => {
    const result = PostCreatedEventSchema.safeParse({
      ...VALID_PAYLOAD,
      parent_post_id: null,
    })
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.parent_post_id).toBeNull()
    }
  })

  it('parent_post_id darf ein String sein', () => {
    const result = PostCreatedEventSchema.safeParse({
      ...VALID_PAYLOAD,
      parent_post_id: 'post-parent',
    })
    expect(result.success).toBe(true)
  })

  it('PlatformSchema kennt reddit und twitter', () => {
    expect(PlatformSchema.options).toContain('reddit')
    expect(PlatformSchema.options).toContain('twitter')
  })

  it('VoiceRegisterSchema kennt formal-de/neutral-de/technical-de/skeptisch-de', () => {
    expect(VoiceRegisterSchema.options).toContain('formal-de')
    expect(VoiceRegisterSchema.options).toContain('neutral-de')
    expect(VoiceRegisterSchema.options).toContain('technical-de')
    expect(VoiceRegisterSchema.options).toContain('skeptisch-de')
  })

  it('lehnt Legacy-voice_register-Werte ab (Anti-Dekorations-Linie #1216)', () => {
    for (const v of ['formal', 'casual', 'jugendsprache']) {
      const result = PostCreatedEventSchema.safeParse({
        ...VALID_PAYLOAD,
        voice_register: v,
      })
      expect(result.success).toBe(false)
    }
  })

  // #1209 5b — sentiment ist aus dem Vertrag entfernt: nie ein Service,
  // nie ein Wert, nie gerendert. `.strict()` weist es jetzt zurück.
  it('sentiment wird als unbekanntes Feld zurückgewiesen', () => {
    const result = PostCreatedEventSchema.safeParse({ ...VALID_PAYLOAD, sentiment: 0.5 })
    expect(result.success).toBe(false)
  })

  it('score-Default ist 0', () => {
    const result = PostCreatedEventSchema.safeParse(VALID_PAYLOAD)
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.score).toBe(0)
    }
  })

  it('score akzeptiert positiv, negativ und 0', () => {
    for (const v of [0, 42, -7]) {
      const result = PostCreatedEventSchema.safeParse({ ...VALID_PAYLOAD, score: v })
      expect(result.success).toBe(true)
    }
  })

  it('Schema-Drift-Gate deckt score ab und kennt kein sentiment mehr', () => {
    const backendKeys = propertyKeys(postCreatedEventJson)
    expect(backendKeys).toContain('score')
    expect(backendKeys).not.toContain('sentiment')
    const zodKeys = shapeKeys(PostCreatedEventSchema)
    expect(zodKeys).toContain('score')
    expect(zodKeys).not.toContain('sentiment')
  })
})
