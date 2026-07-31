/**
 * format.ts — Formatierungs-Utilities für Run-Budgets (Issue #764).
 *
 * Locale wird explizit als 'de-DE' übergeben, damit die Assertions stabil
 * sind. Currency-Strings werden auf NBSP-Varianten normalisiert, weil ICU-
 * Versionen zwischen schmalem/Umbruch-geschütztem Leerzeichen driften —
 * Ziffern und Symbol bleiben exakt geprüft.
 */
import { describe, it, expect } from 'vitest'
import {
  formatTokens,
  formatCostMicros,
  formatDuration,
  formatDurationMs,
  formatRange,
} from '../format'

/** NBSP/narrow-NBSP → normales Leerzeichen (ICU-Drift zwischen Versionen). */
function nbsp(s: string): string {
  return s.replace(/[\u00a0\u202f]/g, ' ')
}

describe('formatTokens', () => {
  it('null/undefined → "—" (niemals 0 für unbekannt)', () => {
    expect(formatTokens(null)).toBe('—')
    expect(formatTokens(undefined)).toBe('—')
  })

  it('unter 1000: ganze Zahl ohne Suffix', () => {
    expect(formatTokens(0)).toBe('0')
    expect(formatTokens(999, 'de-DE')).toBe('999')
  })

  it('ab 1000: k-Suffix mit max. 1 Nachkommastelle', () => {
    expect(formatTokens(1000, 'de-DE')).toBe('1k')
    expect(formatTokens(12_500, 'de-DE')).toBe('12,5k')
  })

  it('ab 1_000_000: M-Suffix mit max. 2 Nachkommastellen', () => {
    expect(formatTokens(1_500_000, 'de-DE')).toBe('1,5M')
    expect(formatTokens(2_340_000, 'de-DE')).toBe('2,34M')
  })
})

describe('formatCostMicros', () => {
  it('null/undefined → "—" (niemals 0 für unbekannt)', () => {
    expect(formatCostMicros(null)).toBe('—')
    expect(formatCostMicros(undefined)).toBe('—')
  })

  it('1_500_000 Micros = 1,50 USD', () => {
    expect(nbsp(formatCostMicros(1_500_000, 'USD', 'de-DE'))).toBe('1,50 $')
  })

  it('0 Micros bleibt 0,00 $ (echte 0 ist zulässig, z. B. free-Tier)', () => {
    expect(nbsp(formatCostMicros(0, 'USD', 'de-DE'))).toBe('0,00 $')
  })

  it('unter einem Cent: 4 Nachkommastellen statt "0,00 $"', () => {
    expect(nbsp(formatCostMicros(4_200, 'USD', 'de-DE'))).toBe('0,0042 $')
  })

  it('genau ein Cent: 2 Nachkommastellen', () => {
    expect(nbsp(formatCostMicros(10_000, 'USD', 'de-DE'))).toBe('0,01 $')
  })
})

describe('formatDuration', () => {
  it('null/undefined → "—"', () => {
    expect(formatDuration(null)).toBe('—')
    expect(formatDuration(undefined)).toBe('—')
  })

  it('unter einer Minute: nur Sekunden', () => {
    expect(formatDuration(0)).toBe('0 s')
    expect(formatDuration(45)).toBe('45 s')
  })

  it('Minuten: "X min" bzw. "X min Y s"', () => {
    expect(formatDuration(60)).toBe('1 min')
    expect(formatDuration(125)).toBe('2 min 5 s')
  })

  it('Stunden: "X h" bzw. "X h Y min" (Sekunden fallen weg)', () => {
    expect(formatDuration(3600)).toBe('1 h')
    expect(formatDuration(3661)).toBe('1 h 1 min')
  })
})

describe('formatDurationMs', () => {
  it('null → "—"', () => {
    expect(formatDurationMs(null)).toBe('—')
  })

  it('Millisekunden werden auf Sekunden umgerechnet', () => {
    expect(formatDurationMs(90_000)).toBe('1 min 30 s')
    expect(formatDurationMs(500)).toBe('1 s')
  })
})

describe('formatRange', () => {
  it('beide Werte null → "—"', () => {
    expect(formatRange(null, null, formatTokens)).toBe('—')
    expect(formatRange(undefined, undefined, formatTokens)).toBe('—')
  })

  it('low und high unterschiedlich → "low – high"', () => {
    expect(formatRange(1000, 5000, formatTokens)).toBe('1k – 5k')
  })

  it('low === high → Einzelwert statt Bereich', () => {
    expect(formatRange(5000, 5000, formatTokens)).toBe('5k')
  })

  it('nur ein Wert gesetzt → Einzelwert', () => {
    expect(formatRange(null, 5000, formatTokens)).toBe('5k')
    expect(formatRange(1000, null, formatTokens)).toBe('1k')
  })
})
