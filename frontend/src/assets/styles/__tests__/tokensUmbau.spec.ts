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

// Ticket 2: die alten Namen zeigen auf die neuen Tokens, kein Rohwert daneben.
describe('alte Token-Namen → neue Tokens (#1795, Ticket 2)', () => {
  const read = (f: string) => readFileSync(resolve(here, '../' + f), 'utf8')
  const v3 = read('tokens-v3.css')
  const compat = read('tokens-compat.css')
  const states = read('states.css')
  const strip = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, '')
  const RAW = /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\boklch\(/
  const declOf = (src: string, name: string): string | undefined =>
    strip(src).match(new RegExp('(?:^|[\\s;{])--' + name + '\\s*:\\s*([^;]+);'))?.[1].trim()

  it.each([['tokens-v3.css', v3], ['tokens-compat.css', compat], ['states.css', states]])(
    '%s enthält keinen Roh-Farbwert (hex, rgb, hsl, oklch)',
    (_n, src) => {
      expect(strip(src)).not.toMatch(RAW)
    },
  )

  it.each(TOKENS)('--%s wird nicht in tokens-v3.css oder tokens-compat.css neu definiert', (name) => {
    for (const src of [v3, compat]) expect(declOf(src, name)).toBeUndefined()
  })

  it('Schrift zeigt auf die Systemschrift, nur die Leseschrift bleibt eigen', () => {
    expect(declOf(v3, 'font-sans')).toBe('var(--ag-font-sans)')
    expect(declOf(v3, 'font-mono')).toBe('var(--ag-font-mono)')
    expect(declOf(v3, 'font-serif')).toMatch(/Newsreader/)
  })

  it('Zustandsfarben sind getrennt: nichts außer Erfolg zeigt auf --ok', () => {
    const all = strip(v3) + strip(compat)
    const pointingAtOk = [...all.matchAll(/(--[\w-]+)\s*:\s*var\(--ok(?:-soft)?\)/g)].map((m) => m[1])
    expect(pointingAtOk.sort()).toEqual(['--status-green', '--status-green-bg'].sort())
    expect(declOf(v3, 'status-orange')).toBe('var(--warn)')
    expect(declOf(v3, 'status-red')).toBe('var(--err)')
  })

  it('„läuft“ ist neutral, kein Zustands- oder Akzent-Token', () => {
    for (const n of ['accent-live', 'accent-live-soft', 'accent-live-text', 'status-teal', 'status-teal-bg']) {
      expect(declOf(v3, n), n).not.toMatch(/--(ok|warn|err|acc)/)
    }
  })

  it('Violett ist der einzige Akzent', () => {
    expect(declOf(v3, 'accent')).toBe('var(--acc)')
    expect(declOf(v3, 'accent-warm')).toBe('var(--acc)')
  })

  it('Schatten zeigen auf die zwei Schatten des Entwurfs oder entfallen', () => {
    expect(declOf(v3, 'shadow-3')).toBe('var(--shadow-pop)')
    expect(declOf(v3, 'shadow-4')).toBe('var(--shadow-dlg)')
    for (const n of ['shadow-1', 'shadow-2', 'shadow-control']) expect(declOf(v3, n)).toBe('none')
  })

  it('die Hülle und der LogDrawer tragen keine Farbwerte mehr', () => {
    const files = [
      '../../../components/LogDrawer.vue',
      '../../../components/v4/shell/AppShell.vue',
      '../../../components/v4/shell/Breadcrumbs.vue',
      '../../../components/v4/shell/CommandPalette.vue',
      '../../../components/v4/shell/Sidebar.vue',
      '../../../components/v4/shell/SidebarGroup.vue',
      '../../../components/v4/shell/SidebarItem.vue',
      '../../../components/v4/shell/Topbar.vue',
    ]
    for (const f of files) {
      const src = readFileSync(resolve(here, f), 'utf8')
        .replace(/\/\*[\s\S]*?\*\//g, '')
        .replace(/<!--[\s\S]*?-->/g, '')
        .replace(/^\s*\/\/.*$/gm, '')
      expect(src, f).not.toMatch(/#[0-9a-fA-F]{6}\b|#(?:[0-9a-fA-F]{3})\b(?!\d)|\brgba?\(|\bhsla?\(/)
    }
  })
})
