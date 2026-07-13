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

  it('Motion-Dauern haben eine Reduced-Motion-Entsprechung', () => {
    const rm = states.match(
      /@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*?--v4-state-motion-duration-fast\s*:/,
    )
    expect(rm, 'kein reduced-motion-Override für Motion-Dauern').not.toBeNull()
  })
})
