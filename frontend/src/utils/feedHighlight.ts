/**
 * feedHighlight — tokenisiert Feed-Beiträge in Text-, Mention- und Hashtag-Segmente.
 *
 * Issue #130: Sichtbarmachung von `@mention` und `#hashtag` im Live-Feed,
 * ohne `v-html` und damit ohne XSS-Vektor — Konsument rendert die Tokens
 * mit `v-for` als `<span>`-Sequenz.
 *
 * Pattern (Bot-Review-Härtung):
 *  - Wortgrenze vorn: nur am String-Anfang oder nach Whitespace (verhindert
 *    Treffer in E-Mail-Adressen wie `user@host.com`).
 *  - Mention: `@` + 0–29 Word/Digit/Punkt-Chars + finaler Word/Digit-Char,
 *    damit ein Satzpunkt am Ende NICHT zur Mention gehört (`@alex.` → `@alex`).
 *  - Hashtag: `#` + 1–30 Word/Digit-Chars (Unicode-tolerant via `\p{L}`).
 *  - Alles andere → text.
 */

const TOKEN_REGEX = /(?<=^|\s)(@[\p{L}\p{N}_.]{0,29}[\p{L}\p{N}_]|#[\p{L}\p{N}_]{1,30})/gu

export interface FeedToken {
  type: 'text' | 'mention' | 'hashtag'
  value: string
}

export function tokenizeFeedText(text: string | null | undefined): FeedToken[] {
  if (!text || typeof text !== 'string') return []
  const tokens: FeedToken[] = []
  let lastIndex = 0
  for (const match of text.matchAll(TOKEN_REGEX)) {
    const value = match[0]
    const start = match.index as number
    if (start > lastIndex) {
      tokens.push({ type: 'text', value: text.slice(lastIndex, start) })
    }
    if (value.startsWith('@')) {
      tokens.push({ type: 'mention', value })
    } else {
      tokens.push({ type: 'hashtag', value })
    }
    lastIndex = start + value.length
  }
  if (lastIndex < text.length) {
    tokens.push({ type: 'text', value: text.slice(lastIndex) })
  }
  return tokens
}
