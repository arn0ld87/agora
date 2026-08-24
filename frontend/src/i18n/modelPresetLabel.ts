/**
 * modelPresetLabel — loest die Anzeigetexte der kuratierten LLM-Presets auf.
 *
 * Issue #1290: `/api/simulation/available-models` lieferte bis dahin fertige
 * `label`-Strings aus `Config.LLM_MODEL_PRESETS` ("Qwen 2.5 14B (lokal,
 * GPU-arm)"). Die wurden unveraendert gerendert und liefen damit komplett am
 * `vue-i18n`-Katalog vorbei — bei Locale `en` stand weiter Deutsch im
 * Dropdown, und die Texte waren ohne Backend-Deploy nicht aenderbar.
 *
 * Der Vertrag liefert jetzt `label_key` (stabil, sprachneutral, Schema
 * `llm.preset.<kind>.<slug>`); der Text lebt in `locales/{de,en}.json`.
 *
 * Aufloesungskette — bewusst identisch zu `components/graph/edgeLabelI18n.ts`:
 *   1. `label_key` + vorhandene Uebersetzung → uebersetzter Text.
 *   2. `label` (Legacy-Feld; nur noch fuer aeltere Backends im Mischbetrieb).
 *   3. `name` — der rohe Modellbezeichner, immer aussagekraeftig.
 */

export interface ModelPresetLike {
  name: string
  label?: string
  label_key?: string
}

/**
 * Uebersetzt ein Preset fuer die Anzeige.
 *
 * @param preset Eintrag aus `presets[]` bzw. `ollama[]` des Endpunkts.
 * @param t vue-i18n `t`-Funktion.
 * @param te optionale vue-i18n `te`-Funktion. Ohne sie wuerde ein im Katalog
 *   fehlender Key `t()` aufrufen und vue-i18n im Dev-Modus eine
 *   "not found"-Warnung loggen, bevor der Fallback greift (Muster aus
 *   Issue #1023, Befund B-04).
 */
export function resolvePresetLabel(
  preset: ModelPresetLike,
  t: (key: string, params?: Record<string, unknown>) => string,
  te?: (key: string) => boolean,
): string {
  const key = preset.label_key
  if (key && typeof t === 'function') {
    const keyExists = typeof te === 'function' ? te(key) : true
    if (keyExists) {
      const translated = t(key)
      // vue-i18n gibt bei Miss den Key selbst zurueck.
      if (translated && translated !== key) return translated
    }
  }
  return preset.label || preset.name
}
