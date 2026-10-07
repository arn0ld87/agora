/**
 * Umrechnung der Budget-Standardgrenzen zwischen Backend-Einheiten
 * (Mikro-USD, Sekunden) und den Eingabeeinheiten der Oberfläche (USD,
 * Minuten/Stunden). Eingaben akzeptieren Komma oder Punkt als Dezimaltrenner.
 */

export type DurationUnit = 'minutes' | 'hours'

const MICROS_PER_USD = 1_000_000
const UNIT_SECONDS: Record<DurationUnit, number> = { minutes: 60, hours: 3600 }

/** Zahl ohne Exponent, ohne überflüssige Nullen (`12.5`, nicht `12.500000`). */
function trimDecimal(value: number, maxDigits: number): string {
  return String(Number(value.toFixed(maxDigits)))
}

/** Mikro-USD → Anzeige in USD (Punkt als Dezimaltrenner, für das Eingabefeld). */
export function microsToUsd(micros: number): string {
  return trimDecimal(micros / MICROS_PER_USD, 6)
}

/** Eingabe in USD → Mikro-USD; `null` bei ungültiger Eingabe (negativ, Text, leer). */
export function usdToMicros(input: string): number | null {
  const n = parseDecimal(input)
  return n === null ? null : Math.round(n * MICROS_PER_USD)
}

/** Sekunden → Einheit und Wert für die Anzeige; volle Stunden werden als Stunden gezeigt. */
export function secondsToDuration(seconds: number): { value: string; unit: DurationUnit } {
  if (seconds > 0 && seconds % UNIT_SECONDS.hours === 0) {
    return { value: String(seconds / UNIT_SECONDS.hours), unit: 'hours' }
  }
  return { value: trimDecimal(seconds / UNIT_SECONDS.minutes, 4), unit: 'minutes' }
}

/** Eingabe + Einheit → Sekunden; `null` bei ungültiger Eingabe. */
export function durationToSeconds(input: string, unit: DurationUnit): number | null {
  const n = parseDecimal(input)
  return n === null ? null : Math.round(n * UNIT_SECONDS[unit])
}

/** Ganze Zahl >= 0 (Tokens, Aufrufe); `null` bei ungültiger Eingabe. */
export function parseWholeNumber(input: string): number | null {
  const trimmed = input.trim()
  if (!/^\d+$/.test(trimmed)) return null
  const n = Number(trimmed)
  return Number.isSafeInteger(n) ? n : null
}

function parseDecimal(input: string): number | null {
  const normalized = input.trim().replace(',', '.')
  if (!/^\d+(\.\d+)?$/.test(normalized)) return null
  const n = Number(normalized)
  return Number.isFinite(n) ? n : null
}
