import { describe, it, expect } from 'vitest'
import {
  coercePositiveInt,
  readRunParamsFromQuery,
  toRunParamsQuery,
  MAX_ROUNDS_QUERY_KEY,
  SIMULATION_DAYS_QUERY_KEY,
  MAX_SIMULATION_DAYS,
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

  it('verwirft verschleierte Zahlenformate', () => {
    // Number() allein parst diese Strings zu gueltigen positiven Ganzzahlen.
    // Eine so getarnte URL darf die eingestellte Rundenzahl nicht ersetzen.
    for (const bad of ['0x10', '1e2', '+5', '5n', '1_000', 'Infinity']) {
      expect(coercePositiveInt(bad)).toBeNull()
    }
  })

  it('verwirft Werte oberhalb der uebergebenen Obergrenze', () => {
    expect(coercePositiveInt('366', MAX_SIMULATION_DAYS)).toBeNull()
    expect(coercePositiveInt(366, MAX_SIMULATION_DAYS)).toBeNull()
    expect(coercePositiveInt('365', MAX_SIMULATION_DAYS)).toBe(365)
    // Ohne Obergrenze bleibt der Wert unangetastet — fuer max_rounds prueft
    // das Backend nur auf "positiv".
    expect(coercePositiveInt('366')).toBe(366)
  })
})

describe('runParamsQuery — Backend-Grenzen', () => {
  // backend/app/api/simulation_run.py lehnt simulation_days > 365 mit einem
  // Fehler ab. Ein durchgereichter Wert laesst damit jeden Startversuch
  // scheitern, statt auf den Auto-Wert zurueckzufallen.
  it('reicht zu grosse Simulationstage nicht aus der URL weiter', () => {
    const params = readRunParamsFromQuery({
      [MAX_ROUNDS_QUERY_KEY]: '20',
      [SIMULATION_DAYS_QUERY_KEY]: '366',
    })
    expect(params.simulationDays).toBeNull()
    expect(params.maxRounds).toBe(20)
  })

  it('schreibt zu grosse Simulationstage nicht in die Query', () => {
    const query = toRunParamsQuery({ maxRounds: 20, simulationDays: 366 })
    expect(query[SIMULATION_DAYS_QUERY_KEY]).toBeUndefined()
    expect(query[MAX_ROUNDS_QUERY_KEY]).toBe('20')
  })

  it('laesst den Grenzwert selbst passieren', () => {
    const query = toRunParamsQuery({ simulationDays: MAX_SIMULATION_DAYS })
    expect(query[SIMULATION_DAYS_QUERY_KEY]).toBe('365')
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
