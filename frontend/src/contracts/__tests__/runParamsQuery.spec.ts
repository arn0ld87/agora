import { describe, it, expect } from 'vitest'
import {
  coercePositiveInt,
  readRunParamsFromQuery,
  toRunParamsQuery,
  MAX_ROUNDS_QUERY_KEY,
  SIMULATION_DAYS_QUERY_KEY,
} from '../runParamsQuery'

describe('runParamsQuery — Normalisierung', () => {
  it('akzeptiert positive Ganzzahlen als Zahl und als String', () => {
    expect(coercePositiveInt(8)).toBe(8)
    expect(coercePositiveInt('8')).toBe(8)
    expect(coercePositiveInt(' 12 ')).toBe(12)
  })

  it('verwirft alles, was keine sinnvolle Rundenzahl ist', () => {
    // 0 und negative Werte würden das Backend in eine Leer-Simulation schicken,
    // Kommazahlen und Müll-Strings stammen aus manipulierten URLs.
    for (const bad of [0, -3, '0', '-1', '2.5', 'abc', '', '   ', null, undefined, true, {}]) {
      expect(coercePositiveInt(bad)).toBeNull()
    }
  })

  it('nimmt bei Mehrfach-Query den ersten Wert', () => {
    expect(coercePositiveInt(['5', '9'])).toBe(5)
  })
})

describe('runParamsQuery — Query-Vertrag', () => {
  it('laesst nicht gesetzte Werte komplett aus der Query', () => {
    // Fehlt der Parameter, gilt bewusst der auto-generierte Wert des Backends.
    expect(toRunParamsQuery({})).toEqual({})
    expect(toRunParamsQuery({ maxRounds: undefined, simulationDays: null })).toEqual({})
  })

  it('serialisiert gesetzte Werte unter den vereinbarten Schluesseln', () => {
    expect(toRunParamsQuery({ maxRounds: 40, simulationDays: 3 })).toEqual({
      [MAX_ROUNDS_QUERY_KEY]: '40',
      [SIMULATION_DAYS_QUERY_KEY]: '3',
    })
  })

  it('liest zurueck, was geschrieben wurde (Roundtrip Step 2 -> Step 3)', () => {
    // Der eigentliche Vertrag: Sender und Empfaenger benutzen dieselben
    // Schluessel. Genau dieser implizite Tausch war vorher gebrochen.
    const query = toRunParamsQuery({ maxRounds: 12, simulationDays: 4 })

    expect(readRunParamsFromQuery(query)).toEqual({ maxRounds: 12, simulationDays: 4 })
  })

  it('meldet fehlende Werte als null statt als 0', () => {
    // null bedeutet "nicht gesetzt" — 0 waere eine gueltige, aber falsche
    // Rundenzahl und wuerde als Wert an das Backend gehen.
    expect(readRunParamsFromQuery({})).toEqual({ maxRounds: null, simulationDays: null })
    expect(readRunParamsFromQuery(undefined)).toEqual({ maxRounds: null, simulationDays: null })
  })
})
