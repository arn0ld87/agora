/**
 * Nur interne Pfade als Weiterleitungsziel (#1617): ``next`` kommt aus der
 * URL und ist damit Nutzereingabe. Absolute URLs, protokollrelative (``//``)
 * und Backslash-Varianten landen auf der Startseite.
 */
export function safeNext(raw: unknown, fallback = '/'): string {
  if (typeof raw !== 'string' || raw.length === 0) return fallback
  if (!raw.startsWith('/') || raw.startsWith('//') || raw.startsWith('/\\')) return fallback
  return raw
}
