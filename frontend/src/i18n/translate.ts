/**
 * translate.ts — Lazy-t()-Wrapper fuer Pinia-Stores und andere Non-Component-Kontexte.
 *
 * Stores koennen nicht `useI18n()` aufrufen (kein Vue-Setup-Kontext).
 * Ein direkter `import i18n from '@/i18n'` loest beim Modul-Import
 * `detectLocale()` → `localStorage.getItem()` aus — was in SSR- und
 * Vitest-Umgebungen vor der jsdom-Initialisierung zu Fehlern fuehrt.
 *
 * Pattern:
 *   1. `main.ts` ruft `registerI18n(i18n.global)` nach `createApp()` auf.
 *   2. Stores importieren `t` aus dieser Datei — kein localStorage-Seiteneffekt.
 *   3. Tests mocken '@/i18n/translate' via vi.mock, oder der Key-Fallback greift.
 *
 * Verwendung in Stores:
 *   import { t } from '@/i18n/translate'
 *   const label = t('cmd.dynamic.runLabel', { name: 'foo' })
 */

type I18nGlobal = {
  t: (key: string, params?: Record<string, unknown>) => string
}

let _global: I18nGlobal | null = null

/**
 * Registriert die i18n-Global-Instanz.
 * Wird einmalig in main.ts nach createApp() aufgerufen.
 */
export function registerI18n(global: I18nGlobal): void {
  _global = global
}

/**
 * Uebersetzt einen i18n-Schluessel mit optionalen Named-Params.
 * Gibt den Key unveraendert zurueck, wenn registerI18n() noch nicht
 * aufgerufen wurde (kein Crash in fruehen Init-Phasen).
 */
export function t(key: string, params?: Record<string, unknown>): string {
  if (!_global) return key
  return _global.t(key, params)
}

/**
 * Setzt den i18n-Global zurueck — fuer Test-Cleanup.
 */
export function _resetI18nGlobal(): void {
  _global = null
}
