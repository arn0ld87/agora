/**
 * edgeLabelI18n — formatiert LLM-generierte Edge-Type-Strings für die Anzeige.
 *
 * Aufrufkontext: D3-Render in `useGraphRender`. Ruf via `formatEdgeLabel(d.name, t)` aus
 * der Vue-Komponente, die `useI18n()` initialisiert hat.
 *
 * Strategie:
 *  1. Exakte i18n-Map prüfen (`graph.edgeLabels.<NORMALIZED>`).
 *  2. Heuristik: UPPER_SNAKE / camelCase → lesbarer Title-Case-String.
 *  3. Fallback: Originalstring.
 *
 * Persistenz in Neo4j bleibt unangetastet — Display only.
 */

const TRANSLATION_PREFIX = 'graph.edgeLabels'

/**
 * Normalisiert einen LLM-generierten Edge-Type für den i18n-Lookup.
 * Beispiele: "Works for" → "WORKS_FOR"; "worksFor" → "WORKS_FOR"; "WORKS_FOR" → "WORKS_FOR".
 * Whitespace und Sonderzeichen werden zu Underscore.
 */
export function normalizeEdgeKey(raw: string | null | undefined): string {
  if (!raw || typeof raw !== 'string') return ''
  return raw
    .trim()
    // camelCase / PascalCase → Snake
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    // Leerzeichen / Bindestriche → Underscore
    .replace(/[\s-]+/g, '_')
    // Mehrfach-Underscore zusammenziehen
    .replace(/_+/g, '_')
    .toUpperCase()
}

/**
 * Heuristik-Fallback: macht aus einem normalisierten Key einen lesbaren String.
 * "WORKS_FOR" → "Works For"; "RELATES_TO" → "Relates To".
 * Bewusst keine Sprachübersetzung — der Heuristik-Pfad ist nur die letzte Reissleine.
 */
export function humanizeEdgeKey(normalizedKey: string): string {
  if (!normalizedKey) return ''
  return normalizedKey
    .split('_')
    .filter(Boolean)
    .map((word) => word.charAt(0) + word.slice(1).toLowerCase())
    .join(' ')
}

/**
 * Formatiert ein Edge-Label für die Anzeige.
 *
 * @param rawName Roh-Label aus dem Graph (`edge.name`).
 * @param t vue-i18n `t`-Funktion (legacy:false → composition API).
 * @param te optionale vue-i18n `te`-Funktion. Issue #1023 (Befund B-04): ohne
 *   `te()`-Guard ruft jede LLM-generierte, nicht in `graph.edgeLabels`
 *   hinterlegte Relation `t(fullKey)` auf — vue-i18n loggt das im Dev-Modus
 *   als "not found"-Warnung, bevor `humanizeEdgeKey()` ueberhaupt greift.
 *   Mit `te` wird der Lookup nur versucht, wenn der Key tatsaechlich existiert.
 * @returns angezeigter String.
 */
export function formatEdgeLabel(
  rawName: string | null | undefined,
  t?: (key: string) => string,
  te?: (key: string) => boolean,
): string {
  if (!rawName || typeof rawName !== 'string') return ''
  const key = normalizeEdgeKey(rawName)
  if (!key) return rawName

  if (typeof t === 'function') {
    const fullKey = `${TRANSLATION_PREFIX}.${key}`
    const keyExists = typeof te === 'function' ? te(fullKey) : true
    if (keyExists) {
      const translated = t(fullKey)
      // vue-i18n gibt bei Miss den Key selbst zurück (oder fallback locale value).
      if (translated && translated !== fullKey) return translated
    }
  }

  return humanizeEdgeKey(key) || rawName
}
