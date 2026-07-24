/**
 * errorLinePattern — Wortgrenzen-bewusstes Matchen von Logzeilen-Token,
 * die typischerweise auf Fehler hindeuten.
 *
 * Vor diesem Fix matchte das Pattern Wort-INNERE Vorkommen, etwa
 * "forwarded", "errorless", "warningless" oder "awareness". Diese
 * Wort-Inneren Treffer führten in LogDrawer, SimulationToolPanel und
 * Step3Simulation zu falsch klassifizierten Error-Zähler und Filter-
 * Ergebnissen.
 *
 * Pattern (Wortgrenzen via \b):
 *  - \b am Anfang: kein Buchstabe/Ziffer vor dem Token.
 *  - \b am Ende:   kein Buchstabe/Ziffer nach dem Token.
 *  - Gleicher Token-Satz in allen Konsumenten (LogDrawer, Step3Simulation,
 *    SimulationToolPanel) — vorher divergierten sie (LogDrawer hatte
 *    warn|warning nicht).
 */
import { describe, it, expect } from 'vitest'

import { isErrorLine, ERROR_PATTERN } from '../errorLinePattern'

describe('errorLinePattern — isErrorLine', () => {
  it('matched "error" als eigenes Wort', () => {
    expect(isErrorLine('error found in module X')).toBe(true)
  })

  it('matched "ERROR" case-insensitiv', () => {
    expect(isErrorLine('ERROR: boom')).toBe(true)
    expect(isErrorLine('Error: boom')).toBe(true)
  })

  it('matched "traceback (most recent call last):"', () => {
    expect(isErrorLine('Traceback (most recent call last):')).toBe(true)
  })

  it('matched "fatal" und "exception"', () => {
    expect(isErrorLine('FATAL: panic')).toBe(true)
    expect(isErrorLine('unhandled exception occurred')).toBe(true)
  })

  it('matched "warning" und "warn"', () => {
    expect(isErrorLine('warning low memory')).toBe(true)
    expect(isErrorLine('WARN: cache stale')).toBe(true)
  })

  it('matched NICHT "forwarded" (Wort-INNERES "error")', () => {
    expect(isErrorLine('forwarded message via relay')).toBe(false)
  })

  it('matched NICHT "errorless" (Wort-INNERES "error")', () => {
    expect(isErrorLine('errorless deployment succeeded')).toBe(false)
  })

  it('matched NICHT "warningless" (Wort-INNERES "warning")', () => {
    expect(isErrorLine('warningless behavior on stage')).toBe(false)
  })

  it('matched NICHT "awareness" (Wort-INNERES "warn")', () => {
    expect(isErrorLine('awareness training scheduled')).toBe(false)
  })

  it('matched NICHT leerer String / kein String', () => {
    expect(isErrorLine('')).toBe(false)
    expect(isErrorLine(null)).toBe(false)
    expect(isErrorLine(undefined)).toBe(false)
    expect(isErrorLine(42)).toBe(false)
  })

  it('matched Token am Zeilen-Anfang und -Ende', () => {
    expect(isErrorLine('error')).toBe(true)
    expect(isErrorLine('error.')).toBe(true)
    expect(isErrorLine('[error]')).toBe(true)
    expect(isErrorLine('log line: error')).toBe(true)
  })
})

describe('errorLinePattern — ERROR_PATTERN', () => {
  it('exportiert das gleiche Pattern, das isErrorLine verwendet', () => {
    expect(ERROR_PATTERN.flags).toContain('i')
    expect(ERROR_PATTERN.source).toBe('\\b(?:error|exception|traceback|fatal|warn|warning)\\b')
  })
})
