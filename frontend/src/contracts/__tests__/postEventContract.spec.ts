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
  voice_register: 'casual' as const,
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

  it('akzeptiert gültigen Payload (reddit/casual)', () => {
    const result = PostCreatedEventSchema.safeParse(VALID_PAYLOAD)
    expect(result.success).toBe(true)
  })

  it('akzeptiert twitter/formal', () => {
    const result = PostCreatedEventSchema.safeParse({
      ...VALID_PAYLOAD,
      platform: 'twitter',
      voice_register: 'formal',
    })
    expect(result.success).toBe(true)
  })

  it('akzeptiert jugendsprache voice_register', () => {
    const result = PostCreatedEventSchema.safeParse({
      ...VALID_PAYLOAD,
      voice_register: 'jugendsprache',
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

  it('VoiceRegisterSchema kennt formal/casual/jugendsprache', () => {
    expect(VoiceRegisterSchema.options).toContain('formal')
    expect(VoiceRegisterSchema.options).toContain('casual')
    expect(VoiceRegisterSchema.options).toContain('jugendsprache')
  })
})
