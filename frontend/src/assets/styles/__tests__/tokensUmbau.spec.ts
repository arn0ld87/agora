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
    // Kommentare im Template zählen nicht. Abschnittsweise statt per Regex,
    // damit kein halb entfernter Kommentar stehen bleiben kann.
    const withoutHtmlComments = (text: string): string =>
      text
        .split('<!--')
        .map((part, i) => {
          if (i === 0) return part
          const end = part.indexOf('-->')
          return end === -1 ? '' : part.slice(end + 3)
        })
        .join('')
    for (const f of files) {
      const src = withoutHtmlComments(readFileSync(resolve(here, f), 'utf8'))
        .replace(/\/\*[\s\S]*?\*\//g, '')
        .replace(/^\s*\/\/.*$/gm, '')
      expect(src, f).not.toMatch(/#[0-9a-fA-F]{6}\b|#(?:[0-9a-fA-F]{3})\b(?!\d)|\brgba?\(|\bhsla?\(/)
    }
  })
})

// Kontrast (WCAG AA, 4.5:1): Zustandstext auf der eigenen -soft-Fläche und
// Fließtext auf den Flächen. Gerechnet aus den oklch-Werten der Datei, damit
// ein Token-Wert den Kontrast nicht still unterschreitet (axe color-contrast).
describe('Kontrast der Token-Paare (WCAG AA)', () => {
  type Rgb = [number, number, number]
  type Paint = { rgb: Rgb; alpha: number }

  const parseOklch = (value: string): Paint => {
    const m = value.match(/^oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+))?\s*\)$/)
    if (!m) throw new Error(`kein oklch-Wert: ${value}`)
    const [L, C, h] = [Number(m[1]), Number(m[2]), (Number(m[3]) * Math.PI) / 180]
    const a = C * Math.cos(h)
    const b = C * Math.sin(h)
    const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    const mm = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3
    const lin = [
      4.0767416621 * l - 3.3077115913 * mm + 0.2309699292 * s,
      -1.2684380046 * l + 2.6097574011 * mm - 0.3413193965 * s,
      -0.0041960863 * l - 0.7034186147 * mm + 1.707614701 * s,
    ].map((v) => Math.min(1, Math.max(0, v)))
    return { rgb: lin as Rgb, alpha: m[4] === undefined ? 1 : Number(m[4]) }
  }
  const gamma = (v: number) => (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055)
  const linear = (v: number) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
  // Wie der Browser: im Gamma-Raum über den Hintergrund legen.
  const over = (fg: Paint, bg: Paint): Paint => ({
    rgb: fg.rgb.map((c, i) => linear(gamma(c) * fg.alpha + gamma(bg.rgb[i]) * (1 - fg.alpha))) as Rgb,
    alpha: 1,
  })
  const luminance = ({ rgb }: Paint) => 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
  const ratio = (a: Paint, b: Paint) => {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
    return (hi + 0.05) / (lo + 0.05)
  }
  const tokenIn = (src: string, name: string) =>
    parseOklch(src.match(new RegExp('--' + name + '\\s*:\\s*([^;]+);'))![1].trim())

  // Dunkel: --err auf --err-soft über --s3 (Hover-Fläche) liegt im Entwurf bei
  // 4.28:1 und bleibt unverändert; Badges sitzen nicht auf --s3.
  const themes = [
    ['Dunkel', dark, ['s0', 's1', 's2']],
    ['Hell', light, ['s0', 's1', 's2', 's3']],
  ] as const

  describe.each(themes)('%s', (_theme, src, stateSurfaces) => {
    it('--ok und --err auf ihrer -soft-Fläche ≥ 4.5:1', () => {
      for (const surface of stateSurfaces) {
        const bg = tokenIn(src, surface)
        for (const state of ['ok', 'err']) {
          const soft = over(tokenIn(src, state + '-soft'), bg)
          expect(ratio(tokenIn(src, state), soft), `--${state} auf --${state}-soft über --${surface}`).toBeGreaterThanOrEqual(4.5)
        }
      }
    })

    it.each(['s0', 's1', 's2', 's3'])('--fg, --fg2, --fg3 und --acc-text auf --%s ≥ 4.5:1', (surface) => {
      const bg = tokenIn(src, surface)
      for (const text of ['fg', 'fg2', 'fg3', 'acc-text']) {
        expect(ratio(tokenIn(src, text), bg), `--${text} auf --${surface}`).toBeGreaterThanOrEqual(4.5)
      }
    })

    it('--on-acc (weiß) auf --acc ≥ 4.5:1', () => {
      const white: Paint = { rgb: [1, 1, 1], alpha: 1 }
      expect(ratio(white, tokenIn(src, 'acc'))).toBeGreaterThanOrEqual(4.5)
    })
  })
})

// Anmeldeseiten: Karte und Text müssen aus denselben Tokens kommen. Die alten
// Catppuccin-Rückfallwerte (--color-*) ergaben im hellen Thema dunkle Schrift
// auf dunkler Karte (#login-heading: 1.08:1).
describe('Anmeldeseiten nutzen Themen-Tokens statt fester Dunkelwerte', () => {
  const views = ['EmailConfirmView', 'LoginView', 'PasswordResetView', 'RegisterView']
  it.each(views)('%s hat keine --color-*-Rückfallwerte oder Roh-Farben', (view) => {
    const src = readFileSync(resolve(here, `../../../views/auth/${view}.vue`), 'utf8')
    const style = src.slice(src.indexOf('<style'))
    expect(style).not.toMatch(/--color-/)
    expect(style).not.toMatch(/#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/)
  })
})

// Das Dokument scrollt, nicht der Hauptbereich: ein eigener Scrollbereich im
// <main> lässt jeden Fokussprung beim Tabben als Sprung nach oben erscheinen
// (Tab-Reihenfolge-Prüfung der e2e-Smokes). Seitenleiste und Kopfzeile bleiben
// per sticky im Bild; die Seitenleiste füllt genau den Viewport.
describe('Hülle: Dokument scrollt, Seitenleiste und Kopfzeile bleiben stehen', () => {
  const shell = readFileSync(resolve(here, '../../../components/v4/shell/AppShell.vue'), 'utf8')
  const rule = (selector: string): string => {
    const start = shell.indexOf(`\n${selector} {`)
    return shell.slice(start, shell.indexOf('}', start))
  }

  it('.app-shell wächst mit dem Inhalt (min-height) und ist kein Scroll-Container', () => {
    const r = rule('.app-shell')
    expect(r).toMatch(/min-height:\s*100dvh/)
    expect(r).not.toMatch(/(^|[\s;])height:/)
    expect(r).toMatch(/overflow:\s*clip/)
  })

  it('der Hauptbereich hat keinen eigenen Scrollbereich', () => {
    expect(rule('.app-shell__main')).not.toMatch(/overflow:\s*(auto|scroll)/)
  })

  it('Seitenleiste und Kopfzeile sind sticky am oberen Rand', () => {
    for (const sel of ['.app-shell__sidebar', '.app-shell__topbar']) {
      expect(rule(sel), sel).toMatch(/position:\s*sticky/)
      expect(rule(sel), sel).toMatch(/top:\s*0/)
    }
    expect(rule('.app-shell__sidebar')).toMatch(/height:\s*100dvh/)
  })
})
