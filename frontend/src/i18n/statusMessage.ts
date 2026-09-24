/**
 * statusMessage — loest serverseitige Status-/Fortschrittsmeldungen auf, die
 * einen ``message_key`` mitliefern (Issue #1174, Muster aus #1458).
 *
 * Das Backend liefert fuer nutzersichtbare Status-Felder zwei Werte:
 *   - ``message_key``: stabiler, sprachneutraler Schluessel (z. B. `report.generated`).
 *   - ``message``: Klartext-Fallback (haeufig Englisch), fuer Consumer ohne
 *     Key-Kenntnis.
 *
 * Aufloesungskette — bewusst identisch zu `modelPresetLabel.ts` /
 * `components/graph/edgeLabelI18n.ts`:
 *   1. ``message_key`` + vorhandene Uebersetzung → uebersetzter Text.
 *   2. ``message`` — der mitgelieferte Klartext.
 */

export interface StatusMessageLike {
  message_key?: string | null
  message?: string | null
}

/**
 * Uebersetzt eine Status-/Fortschrittsmeldung fuer die Anzeige.
 *
 * @param data Antwortobjekt mit ``message_key``/``message`` (z. B. `TaskStatusData`, `ReportStatusData`).
 * @param t vue-i18n `t`-Funktion.
 * @param te optionale vue-i18n `te`-Funktion. Ohne sie wuerde ein im Katalog
 *   fehlender Key `t()` aufrufen und vue-i18n im Dev-Modus eine
 *   "not found"-Warnung loggen, bevor der Fallback greift (Muster aus
 *   Issue #1023, Befund B-04).
 */
export function resolveStatusMessage(
  data: StatusMessageLike | null | undefined,
  t: (key: string, params?: Record<string, unknown>) => string,
  te?: (key: string) => boolean,
): string {
  if (!data) return ''
  const key = data.message_key
  if (key && typeof t === 'function') {
    const keyExists = typeof te === 'function' ? te(key) : true
    if (keyExists) {
      const translated = t(key)
      // vue-i18n gibt bei Miss den Key selbst zurueck.
      if (translated && translated !== key) return translated
    }
  }
  return data.message || ''
}
