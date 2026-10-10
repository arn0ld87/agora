/**
 * UAT-001 — Die wirksame Persona-Schwelle ist min(20, Obergrenze).
 *
 * Der Erstellungsdialog nannte als einzige Mindestzahl 10 und nie die
 * Schwelle, an der der Bericht gemessen wird. Der Lauf endete mit
 * „18/20 Personas vorhanden" und ohne Berichtstext, nachdem die Pipeline
 * bereits Kosten verursacht hatte.
 */
import { describe, it, expect } from 'vitest'

import {
  MIN_PERSONA_TABLE_ROWS,
  MIN_SIMULATION_AGENTS,
  effectivePersonaFloor,
} from '../personaFloor'

describe('effectivePersonaFloor', () => {
  it('ohne Obergrenze gilt der Contract-Wert', () => {
    expect(effectivePersonaFloor(null)).toBe(MIN_PERSONA_TABLE_ROWS)
    expect(effectivePersonaFloor(undefined)).toBe(MIN_PERSONA_TABLE_ROWS)
    expect(effectivePersonaFloor(0)).toBe(MIN_PERSONA_TABLE_ROWS)
  })

  it('eine kleinere Obergrenze senkt die Schwelle auf deren Wert', () => {
    expect(effectivePersonaFloor(MIN_SIMULATION_AGENTS)).toBe(MIN_SIMULATION_AGENTS)
    expect(effectivePersonaFloor(15)).toBe(15)
  })

  it('eine positive Obergrenze unter 10 folgt dem Backend-Minimum', () => {
    expect(effectivePersonaFloor(1)).toBe(MIN_SIMULATION_AGENTS)
    expect(effectivePersonaFloor(5)).toBe(MIN_SIMULATION_AGENTS)
    expect(effectivePersonaFloor(9)).toBe(MIN_SIMULATION_AGENTS)
  })

  it('eine größere Obergrenze hebt die Schwelle nicht über den Contract', () => {
    expect(effectivePersonaFloor(30)).toBe(MIN_PERSONA_TABLE_ROWS)
    expect(effectivePersonaFloor(500)).toBe(MIN_PERSONA_TABLE_ROWS)
  })
})
