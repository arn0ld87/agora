/**
 * Format-Utilities für Run-Budgets (Issue #764).
 *
 * Reine Darstellungslogik — keine Geschäftslogik, keine Preisberechnung
 * (Preise kommen ausschließlich als Micros aus dem Backend-Contract).
 * Unbekannte Werte (null/undefined) werden nie als 0 gerendert.
 */

/** 12.500 Token → "12,5k" / "12.5k" je nach Locale. */
export function formatTokens(
  tokens: number | null | undefined,
  locale = 'de-DE',
): string {
  if (tokens === null || tokens === undefined) return '—';
  if (tokens < 1000) {
    return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(
      tokens,
    );
  }
  if (tokens < 1_000_000) {
    return `${new Intl.NumberFormat(locale, {
      maximumFractionDigits: 1,
    }).format(tokens / 1000)}k`;
  }
  return `${new Intl.NumberFormat(locale, {
    maximumFractionDigits: 2,
  }).format(tokens / 1_000_000)}M`;
}

/**
 * Integer-Micros → Währungsstring.
 * 1_500_000 Micros = 1,50 USD → "1,50 $".
 * Unter einem Cent wird auf 4 Nachkommastellen gerundet, damit kleine
 * Schätzwerte nicht als "0,00 $" erscheinen.
 */
export function formatCostMicros(
  micros: number | null | undefined,
  currency = 'USD',
  locale = 'de-DE',
): string {
  if (micros === null || micros === undefined) return '—';
  const amount = micros / 1_000_000;
  const digits = amount > 0 && amount < 0.01 ? 4 : 2;
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: digits,
  }).format(amount);
}

/** Sekunden → "1 h 23 min" / "45 s" (kompakt, deutsch). */
export function formatDuration(
  seconds: number | null | undefined,
): string {
  if (seconds === null || seconds === undefined) return '—';
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return minutes > 0 ? `${hours} h ${minutes} min` : `${hours} h`;
  if (minutes > 0) return secs > 0 ? `${minutes} min ${secs} s` : `${minutes} min`;
  return `${secs} s`;
}

/** Millisekunden → formatDuration. */
export function formatDurationMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—';
  return formatDuration(ms / 1000);
}

/**
 * Bereichsformatierung für Schätzungen: "12k – 40k".
 * Beide null → "—"; nur ein Wert → Einzelwert.
 */
export function formatRange(
  low: number | null | undefined,
  high: number | null | undefined,
  format: (value: number | null | undefined) => string,
): string {
  const lowSet = low !== null && low !== undefined;
  const highSet = high !== null && high !== undefined;
  if (!lowSet && !highSet) return '—';
  if (lowSet && highSet && low !== high) {
    return `${format(low)} – ${format(high)}`;
  }
  return format(lowSet ? low : high);
}
