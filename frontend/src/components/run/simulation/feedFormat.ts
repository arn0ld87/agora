/** Kleine Anzeige-Helfer für die Feed-Oberfläche (#1801). */

/** Kurze, lokalisierte Zeitangabe; ein unlesbarer Zeitstempel erscheint unverändert. */
export function formatPostTime(iso: string, locale: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return new Intl.DateTimeFormat(locale, { dateStyle: 'short', timeStyle: 'short' }).format(date)
}
