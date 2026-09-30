/**
 * Zod-Spiegel-Drift-Tests für SimAction-Verträge.
 *
 * #1713 · Schema-Quellen:
 *   schemas/sim-action-record.schema.json
 *   schemas/sim-action-page.schema.json
 *   schemas/round-summary.schema.json
 *
 * Prüft:
 * 1. Schema-Drift-Gate: alle Backend-Properties sind im Zod-Spiegel vorhanden.
 * 2. Sample-Payloads werden korrekt geparst.
 * 3. Pflichtfehler und unbekannte Felder werden abgelehnt.
 */

import { describe, it, expect } from 'vitest'
import {
  SimActionTypeSchema,
  SimActionRecordSchema,
  SimActionPageSchema,
  RoundSummarySchema,
  RoundsResponseSchema,
} from '../simActionContract'
import simActionRecordJson from '../../../../schemas/sim-action-record.schema.json'
import simActionPageJson from '../../../../schemas/sim-action-page.schema.json'
import roundSummaryJson from '../../../../schemas/round-summary.schema.json'

function propertyKeys(schema: { properties?: Record<string, unknown> }) {
  return Object.keys(schema.properties ?? {}).sort()
}

function shapeKeys(schema: { shape: Record<string, unknown> }) {
  return Object.keys(schema.shape).sort()
}

// --- Sample Payloads --------------------------------------------------------

const VALID_ACTION: Record<string, unknown> = {
  round_num: 1,
  timestamp: '2026-09-30T10:00:00+00:00',
  platform: 'twitter',
  agent_id: 'agent-1',
  agent_name: 'Mara Lindner',
  action_type: 'CREATE_POST',
}

const VALID_PAGE: Record<string, unknown> = {
  items: [VALID_ACTION],
  next_cursor: null,
}

const VALID_ROUND_SUMMARY: Record<string, unknown> = {
  round_num: 0,
  platform: 'reddit',
  action_counts: { CREATE_POST: 3, LIKE_POST: 7 },
}

// --- SimActionTypeSchema ----------------------------------------------------

describe('SimActionTypeSchema', () => {
  it('kennt alle 17 Aktionsarten inkl. OTHER', () => {
    const types = SimActionTypeSchema.options
    expect(types).toContain('CREATE_POST')
    expect(types).toContain('OTHER')
    expect(types).toHaveLength(17)
  })

  it('lehnt unbekannte Aktionsart ab', () => {
    expect(SimActionTypeSchema.safeParse('UNKNOWN_ACTION').success).toBe(false)
  })
})

// --- SimActionRecordSchema --------------------------------------------------

describe('SimActionRecordSchema', () => {
  it('Schema-Drift-Gate: Zod-Spiegel deckt alle Backend-Properties ab', () => {
    const backendKeys = propertyKeys(simActionRecordJson)
    const zodKeys = shapeKeys(SimActionRecordSchema)
    for (const key of backendKeys) {
      expect(zodKeys, `Feld "${key}" fehlt im Zod-Spiegel`).toContain(key)
    }
  })

  it('akzeptiert minimalen gültigen Payload', () => {
    const result = SimActionRecordSchema.safeParse(VALID_ACTION)
    expect(result.success).toBe(true)
  })

  it('akzeptiert Payload mit optionalen Feldern', () => {
    const result = SimActionRecordSchema.safeParse({
      ...VALID_ACTION,
      content: 'Ein Post-Text',
      success: false,
      sim_time: '2026-09-30T09:55:00+00:00',
      role_conflict: 'foreign_role',
      target_post_id: 'post-42',
    })
    expect(result.success).toBe(true)
  })

  it('success defaultet auf true', () => {
    const result = SimActionRecordSchema.safeParse(VALID_ACTION)
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.success).toBe(true)
    }
  })

  it('content defaultet auf null', () => {
    const result = SimActionRecordSchema.safeParse(VALID_ACTION)
    if (result.success) {
      expect(result.data.content).toBeNull()
    }
  })

  it('lehnt unbekannte Plattform ab', () => {
    expect(
      SimActionRecordSchema.safeParse({ ...VALID_ACTION, platform: 'mastodon' }).success
    ).toBe(false)
  })

  it('lehnt unbekannte Aktionsart ab', () => {
    expect(
      SimActionRecordSchema.safeParse({ ...VALID_ACTION, action_type: 'INVALID' }).success
    ).toBe(false)
  })

  it('lehnt negativen round_num ab', () => {
    expect(
      SimActionRecordSchema.safeParse({ ...VALID_ACTION, round_num: -1 }).success
    ).toBe(false)
  })

  it('lehnt unbekannte Felder ab (strict)', () => {
    expect(
      SimActionRecordSchema.safeParse({ ...VALID_ACTION, extra: 'x' }).success
    ).toBe(false)
  })

  it('lehnt ungültigen role_conflict-Wert ab', () => {
    expect(
      SimActionRecordSchema.safeParse({ ...VALID_ACTION, role_conflict: 'bad_value' }).success
    ).toBe(false)
  })
})

// --- SimActionPageSchema ----------------------------------------------------

describe('SimActionPageSchema', () => {
  it('Schema-Drift-Gate: Zod-Spiegel deckt alle Backend-Properties ab', () => {
    const backendKeys = propertyKeys(simActionPageJson)
    const zodKeys = shapeKeys(SimActionPageSchema)
    for (const key of backendKeys) {
      expect(zodKeys, `Feld "${key}" fehlt im Zod-Spiegel`).toContain(key)
    }
  })

  it('akzeptiert gültige Seite mit Items', () => {
    const result = SimActionPageSchema.safeParse(VALID_PAGE)
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.items).toHaveLength(1)
    }
  })

  it('akzeptiert leere Items-Liste', () => {
    const result = SimActionPageSchema.safeParse({ items: [], next_cursor: null })
    expect(result.success).toBe(true)
  })

  it('next_cursor defaultet auf null', () => {
    const result = SimActionPageSchema.safeParse({ items: [] })
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.next_cursor).toBeNull()
    }
  })

  it('next_cursor kann ein String sein', () => {
    const result = SimActionPageSchema.safeParse({ items: [], next_cursor: 'cursor-abc' })
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.next_cursor).toBe('cursor-abc')
    }
  })

  it('lehnt unbekannte Felder ab (strict)', () => {
    expect(
      SimActionPageSchema.safeParse({ ...VALID_PAGE, extra: 'x' }).success
    ).toBe(false)
  })
})

// --- RoundSummarySchema -----------------------------------------------------

describe('RoundSummarySchema', () => {
  it('Schema-Drift-Gate: Zod-Spiegel deckt alle Backend-Properties ab', () => {
    const backendKeys = propertyKeys(roundSummaryJson)
    const zodKeys = shapeKeys(RoundSummarySchema)
    for (const key of backendKeys) {
      expect(zodKeys, `Feld "${key}" fehlt im Zod-Spiegel`).toContain(key)
    }
  })

  it('akzeptiert gültige Runden-Zusammenfassung', () => {
    const result = RoundSummarySchema.safeParse(VALID_ROUND_SUMMARY)
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.action_counts['CREATE_POST']).toBe(3)
    }
  })

  it('action_counts defaultet auf {}', () => {
    const result = RoundSummarySchema.safeParse({ round_num: 0, platform: 'reddit' })
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.action_counts).toEqual({})
    }
  })

  it('lehnt negativen round_num ab', () => {
    expect(
      RoundSummarySchema.safeParse({ ...VALID_ROUND_SUMMARY, round_num: -1 }).success
    ).toBe(false)
  })

  it('lehnt unbekannte Felder ab (strict)', () => {
    expect(
      RoundSummarySchema.safeParse({ ...VALID_ROUND_SUMMARY, extra: 'x' }).success
    ).toBe(false)
  })
})

// --- RoundsResponseSchema ---------------------------------------------------

describe('RoundsResponseSchema', () => {
  it('akzeptiert leere Rounds-Liste', () => {
    const result = RoundsResponseSchema.safeParse({ rounds: [] })
    expect(result.success).toBe(true)
  })

  it('akzeptiert Rounds mit RoundSummary-Einträgen', () => {
    const result = RoundsResponseSchema.safeParse({
      rounds: [VALID_ROUND_SUMMARY, { round_num: 1, platform: 'twitter' }],
    })
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.rounds).toHaveLength(2)
    }
  })

  it('lehnt unbekannte Felder ab (strict)', () => {
    expect(
      RoundsResponseSchema.safeParse({ rounds: [], extra: 'x' }).success
    ).toBe(false)
  })
})
