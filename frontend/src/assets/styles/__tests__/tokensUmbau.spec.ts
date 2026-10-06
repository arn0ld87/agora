import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

// Frontend-Umbau (#1795), Ticket 1: die 26 Tokens des Entwurfs stehen in
// einem Dunkel- und einem Hell-Block, dazu Schrift und Radien.

const here = dirname(fileURLToPath(import.meta.url))
const css = readFileSync(resolve(here, '../tokens-umbau.css'), 'utf8')
const main = readFileSync(resolve(here, '../../../main.ts'), 'utf8')

const TOKENS = [
  's0', 's1', 's2', 's3', 's4', 'field', 'line',
  'fg', 'fg2', 'fg3',
  'acc', 'acc-hover', 'acc-press', 'acc-text', 'acc-soft', 'acc-line', 'on-acc',
  'ok', 'ok-soft', 'warn', 'warn-soft', 'err', 'err-soft',
  'scrim', 'shadow-pop', 'shadow-dlg',
] as const

const block = (selector: string): string => {
  const start = css.indexOf(selector + ' {')
  expect(start, `Block ${selector} fehlt`).toBeGreaterThanOrEqual(0)
  return css.slice(start, css.indexOf('\n}', start))
}
const dark = block(':root, [data-theme="dark"]')
const light = block('[data-theme="light"]')
const def = (name: string) => new RegExp('--' + name + '\\s*:\\s*[^;]+;')

describe('tokens-umbau.css', () => {
  it('hat genau 26 Tokens in der Liste', () => {
    expect(new Set(TOKENS).size).toBe(26)
  })

  it.each(TOKENS)('definiert --%s im Dunkel- und im Hell-Block', (name) => {
    expect(dark).toMatch(def(name))
    expect(light).toMatch(def(name))
  })

  it('Hell weicht bei den Farbwerten von Dunkel ab', () => {
    for (const name of TOKENS.filter((n) => n !== 'on-acc')) {
      const d = dark.match(new RegExp('--' + name + '\\s*:\\s*([^;]+);'))![1]
      const l = light.match(new RegExp('--' + name + '\\s*:\\s*([^;]+);'))![1]
      expect(l, `--${name} ist in Hell und Dunkel gleich`).not.toBe(d)
    }
  })

  it('Farbwerte sind oklch (außer --on-acc)', () => {
    for (const name of TOKENS.filter((n) => !['on-acc', 'shadow-pop', 'shadow-dlg'].includes(n))) {
      expect(dark.match(new RegExp('--' + name + '\\s*:\\s*([^;]+);'))![1]).toMatch(/^oklch\(/)
    }
  })

  it('definiert Systemschrift, Festbreite und die sechs Radien mit eigenen Namen', () => {
    expect(dark).toMatch(/--ag-font-sans\s*:[^;]*-apple-system[^;]*Segoe UI Variable[^;]*system-ui/)
    expect(dark).toMatch(/--ag-font-mono\s*:[^;]*ui-monospace[^;]*SF Mono[^;]*Menlo/)
    const radii = ['6', '8', '10', '12', '16'].map((n) =>
      dark.match(new RegExp('--ag-r-' + n + '\\s*:\\s*(\\d+)px'))?.[1],
    )
    expect(radii).toEqual(['6', '8', '10', '12', '16'])
    expect(dark).toMatch(/--ag-r-pill\s*:\s*999px/)
  })

  it('setzt color-scheme je Block', () => {
    expect(dark).toMatch(/color-scheme:\s*dark/)
    expect(light).toMatch(/color-scheme:\s*light/)
  })

  it('wird in main.ts vor tokens-compat.css importiert', () => {
    const u = main.indexOf("tokens-umbau.css'")
    const c = main.indexOf("tokens-compat.css'")
    expect(u).toBeGreaterThan(-1)
    expect(u).toBeLessThan(c)
  })
})
