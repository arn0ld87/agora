import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

// Contract-Test für Slice 7.1 — Additive Golden-Gate-Tokens und State-Verträge.
// Liest die beiden globalen CSS-Sources-of-Truth und fordert die vereinbarten
// semantischen Tokens, den Focus-Kontrast, die Reduced-Motion-Entsprechung und
// das Verbot neuer Namespace-Präfixe. Bestehende Tokenwerte werden nicht geprüft
// (rein additive Erweiterung, kein Migrationsvertrag).

const here = dirname(fileURLToPath(import.meta.url))
const tokens = readFileSync(resolve(here, '../tokens-v3.css'), 'utf8')
const states = readFileSync(resolve(here, '../states.css'), 'utf8')

const def = (name: string) => new RegExp(name.replace(/-/g, '\\-') + '\\s*:')

describe('Slice 7.1 — Golden-Gate additive Tokens (tokens-v3.css)', () => {
  const surface = ['--surface-glass', '--surface-glass-strong', '--surface-backdrop']
  const accent = ['--accent-warm', '--accent-warm-hover']
  const status = ['--status-coral', '--status-coral-bg']
  const focus = ['--focus-ring-strong']
  const all = [...surface, ...accent, ...status, ...focus]

  it.each(all)('definiert %s', (name) => {
    expect(tokens).toMatch(def(name))
  })

  it('neue Tokens bleiben in bestehenden Präfix-Familien', () => {
    const allowed = /^--(surface|accent|status|focus)-/
    for (const n of all) expect(n).toMatch(allowed)
  })

  it('führt keine --golden-* oder --a26-* Präfixe ein', () => {
    expect(tokens).not.toMatch(/--golden-/)
    expect(tokens).not.toMatch(/--a26-/)
    expect(states).not.toMatch(/--golden-/)
    expect(states).not.toMatch(/--a26-/)
  })
})

describe('Slice 7.1 — Motion- & Focus-Vertrag (states.css)', () => {
  const motion = [
    '--v4-state-motion-duration-fast',
    '--v4-state-motion-duration-base',
    '--v4-state-motion-duration-slow',
    '--v4-state-motion-ease',
  ]

  it.each(motion)('definiert %s unter bestehendem --v4-state-Präfix', (name) => {
    expect(states).toMatch(def(name))
  })

  it('Focus-Indikator ist mindestens 2px', () => {
    const m = states.match(/--v4-state-focus-ring-strong-width\s*:\s*(\d+)px/)
    expect(m, 'focus-ring-strong-width fehlt').not.toBeNull()
    expect(Number(m![1])).toBeGreaterThanOrEqual(2)
  })

  // Reduce-Motion-Klausel: alle drei Motion-Dauern müssen im
  // prefers-reduced-motion-Block auf einen Nicht-Animations-Wert
  // (0 oder nahe 0) gesetzt sein. Vorher nur 'fast' geprüft.
  it.each(['fast', 'base', 'slow'])(
    'prefers-reduced-motion überschreibt --v4-state-motion-duration-%s',
    (variant) => {
      const re = new RegExp(
        '@media\\s*\\(prefers-reduced-motion:\\s*reduce\\)' +
          '[\\s\\S]*?--v4-state-motion-duration-' +
          variant +
          '\\s*:',
      )
      expect(states.match(re), `Reduce-Override für duration-${variant} fehlt`).not.toBeNull()
    },
  )

  it('Reduce-Werte sind tatsächlich deaktiviert (≤ 0.01 ms)', () => {
    const reduceBlock = states.match(
      /@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*?(?=@media|\n\})/,
    )
    expect(reduceBlock, 'Reduce-Block fehlt').not.toBeNull()
    for (const v of ['fast', 'base', 'slow']) {
      const m = reduceBlock![0].match(
        new RegExp('--v4-state-motion-duration-' + v + '\\s*:\\s*([\\d.]+)\\s*(ms|s)?'),
      )
      expect(m, `Reduce-Override für ${v} fehlt`).not.toBeNull()
      const num = Number(m![1])
      const unit = m![2] || 'ms'
      // Etablierte Reduce-Motion-Konvention: 0.01ms (oder 0s / 0 ohne Einheit).
      // Wir akzeptieren alles ≤ 0.01ms als „effektiv aus“.
      const ms = unit === 's' ? num * 1000 : num
      expect(ms, `Reduce-Wert für ${v} (${ms}ms) ist nicht effektiv 0`).toBeLessThanOrEqual(0.01)
    }
  })
})

// Fokus-Vertrag: --focus-ring-strong ist ein dedizierter, sichtbar
// verifizierter Token — nicht nur in der Sammel-Definitions-Liste.
// Erzwingt zusätzlich zur Existenz ein gültiges RGBA-Format mit Alpha
// ≥ 0.5, damit "strong" tatsächlich mehr Kontrast bedeutet als der
// normale --focus-ring (Alpha 0.35). Verhindert zukünftiges Drift bei
// versehentlichen Wertänderungen.
describe('Slice 7.1 — Focus-Vertrag (tokens-v3.css)', () => {
  it('--focus-ring-strong ist dediziert definiert', () => {
    expect(tokens).toMatch(def('--focus-ring-strong'))
  })

  it('--focus-ring-strong hat ein gültiges RGBA-Format', () => {
    const m = tokens.match(/--focus-ring-strong\s*:\s*([^;]+);/)
    expect(m, '--focus-ring-strong fehlt').not.toBeNull()
    const rgba = m![1].trim().match(
      /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)$/,
    )
    expect(rgba, `--focus-ring-strong hat kein gültiges RGBA-Format: "${m![1].trim()}"`).not.toBeNull()
  })

  it('--focus-ring-strong hat Alpha ≥ 0.5 (stärker als --focus-ring mit 0.35)', () => {
    const m = tokens.match(/--focus-ring-strong\s*:\s*rgba?\([^)]+\)/)
    expect(m, '--focus-ring-strong fehlt').not.toBeNull()
    const alpha = m![0].match(/,\s*([\d.]+)\s*\)$/)
    expect(alpha, 'Alpha-Komponente fehlt').not.toBeNull()
    expect(
      Number(alpha![1]),
      `--focus-ring-strong Alpha ${alpha![1]} ist < 0.5 — verliert "strong"-Bedeutung`,
    ).toBeGreaterThanOrEqual(0.5)
  })
})

// Dark-Readiness-Klausel: Sobald ein [data-theme="dark"]-Block in
// tokens-v3.css existiert, müssen die vier theme-starken Farbwerte
// (--accent-warm-hover, --status-coral, --status-coral-bg,
// --focus-ring-strong) im Dark-Block redefiniert sein — sonst driften
// sie im Dark-Mode auf die Light-Werte. Bis es keinen Dark-Block gibt,
// ist die Klausel trivial erfüllt.
describe('Slice 7.1 — Dark-Readiness-Klausel (tokens-v3.css)', () => {
  const mustOverrideInDark = [
    '--accent-warm-hover',
    '--status-coral',
    '--status-coral-bg',
    '--focus-ring-strong',
  ] as const

  it.each(mustOverrideInDark)(
    'wenn [data-theme="dark"] existiert, muss %s darin redefiniert sein',
    (name) => {
      // Block B1: tokens-v3.css hat MEHRERE Selektoren mit
      // [data-theme="dark"] (Basis, Kompat-Layer, Slice-7.1-Additive).
      // Die Klausel gilt über alle zusammen — ein Token darf in jedem
      // von ihnen definiert sein, nur eben nicht ausschliesslich in
      // einem Light-Block.
      const darkBlocks = [
        ...tokens.matchAll(/\[data-theme="dark"\][^{]*\{([\s\S]*?)\n\}/g),
      ].map((m) => m[1])
      if (darkBlocks.length === 0) {
        // Kein Dark-Block → Klausel trivial erfüllt, kein Fail.
        return
      }
      const re = new RegExp(name.replace(/-/g, '\\-') + '\\s*:')
      expect(
        darkBlocks.join('\n').match(re),
        `${name} ist in keinem [data-theme="dark"]-Block redefiniert`,
      ).not.toBeNull()
    },
  )
})

// Redesign 2026-09, PR 1 — Typo-Skala, Radius-Skala, Label-Stil, Compat-Split.
// Vertrag: docs/ui/premium-redesign-2026-09/01-visual-audit.md, §4.
describe('Redesign PR 1 — Typo- und Radius-Skala (tokens-v3.css)', () => {
  const compat = readFileSync(resolve(here, '../tokens-compat.css'), 'utf8')
  const scale = ['display', 'title', 'heading', 'body', 'small', 'label', 'prose', 'mono', 'mono-lg']

  it.each(scale)('definiert --fs-%s', (role) => {
    expect(tokens).toMatch(def(`--fs-${role}`))
  })

  it('--fs-display ist fluid (clamp) und bricht Titel nicht Wort für Wort', () => {
    expect(tokens).toMatch(/--fs-display\s*:\s*clamp\(/)
  })

  it('Radius-Skala hat genau die Stufen 4 / 6 / 10 / pill', () => {
    const native = tokens.match(/--r-[a-z0-9]+\s*:\s*[^;]+;/g) ?? []
    const values = native.map((d) => d.replace(/^[^:]+:\s*/, '').replace(/;$/, '').trim())
    expect(new Set(values)).toEqual(new Set(['4px', '6px', '10px', '9999px']))
  })

  it('Compat-Radien zeigen nur auf Skalenstufen', () => {
    for (const m of compat.matchAll(/--r-\d+\s*:\s*([^;]+);/g)) {
      expect(m[1].trim()).toMatch(/^var\(--r-(2|3|5)\)$/)
    }
  })

  it('.t-label ist Satzschrift ohne Versalien', () => {
    const block = tokens.match(/\.t-label\s*\{([\s\S]*?)\}/)
    expect(block).not.toBeNull()
    expect(block![1]).toMatch(/text-transform:\s*none/)
    expect(block![1]).toMatch(/var\(--font-sans\)/)
  })

  it('tokens-compat.css trägt nur Aliase und alte Größennamen, keine neuen Farbwerte', () => {
    const hexes = compat.match(/#[0-9a-fA-F]{3,8}\b/g) ?? []
    // --ink-800/--ink-900 sind die einzigen Rohwerte, die noch aus v2 stammen.
    expect(hexes.length).toBeLessThanOrEqual(2)
    expect(compat).not.toMatch(/--(golden|a26|mesh|glow-info)-/)
  })

  it('tokens-v3.css trägt keine Mesh-, Grid- oder Glow-Tokens mehr', () => {
    expect(tokens).not.toMatch(/--mesh-|--bg-grid|--grid-cols|--glow-/)
  })
})
