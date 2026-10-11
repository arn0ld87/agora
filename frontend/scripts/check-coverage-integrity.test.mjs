// Tests fuer check-coverage-integrity.mjs (Issue #1672).
// Runner: bun:test, immer mit explizitem Pfad aufrufen
//   bun test ./scripts/check-coverage-integrity.test.mjs
// (Vitest sammelt scripts/ nicht ein: test.include deckt nur src/ und tests/ ab.)
import { afterEach, beforeEach, describe, expect, test } from 'bun:test'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'

import { checkIntegrity, maskSource, readActiveScope } from './check-coverage-integrity.mjs'

const INCLUDE = ['src/**/*.{js,ts,vue}']
const EXCLUDE = ['src/**/*.{test,spec}.{js,ts}', 'src/main.{js,ts}']

function viteConfig({ include = INCLUDE, exclude = EXCLUDE } = {}) {
  const list = (items) => items.map((item) => `'${item}'`).join(', ')
  return `const coverageBaseline = JSON.parse(readFileSync('coverage-baseline.json', 'utf-8'))
export default {
  test: {
    include: ['src/**/*.{test,spec}.{js,ts}'],
    exclude: ['node_modules/**'],
    coverage: {
      provider: 'v8',
      include: [${list(include)}],
      exclude: [
        // Kommentar im Array
        ${exclude.map((item) => `'${item}'`).join(',\n        ')},
      ],
      thresholds: { lines: coverageBaseline.line_min, functions: 28, branches: coverageBaseline.branch_min, statements: 28 },
    },
  },
}
`
}

function baseline(overrides = {}) {
  return {
    line_min: 83.57,
    branch_min: 73.32,
    lowering_approval: null,
    scope: { include: [...INCLUDE], exclude: [...EXCLUDE] },
    ...overrides,
  }
}

let root

function put(rel, content) {
  const target = join(root, rel)
  mkdirSync(dirname(target), { recursive: true })
  writeFileSync(target, typeof content === 'string' ? content : `${JSON.stringify(content, null, 2)}\n`)
}

function setup({ config = viteConfig(), base = baseline(), allowlist = { entries: [] }, files = {} } = {}) {
  put('vite.config.js', config)
  put('coverage-baseline.json', base)
  put('coverage-skip-allowlist.json', allowlist)
  put('src/a.test.js', "it('laeuft', () => {})\n")
  for (const [rel, content] of Object.entries(files)) put(rel, content)
}

const noBase = () => null

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), 'cov-integrity-'))
})

afterEach(() => {
  rmSync(root, { recursive: true, force: true })
})

describe('Scope', () => {
  test('unveraenderter Stand geht durch', () => {
    setup()
    const result = checkIntegrity({ root, readBase: () => baseline() })
    expect(result.errors).toEqual([])
  })

  test('neues exclude-Muster in vite.config.js faellt durch', () => {
    setup({ config: viteConfig({ exclude: [...EXCLUDE, 'src/components/**'] }) })
    const result = checkIntegrity({ root, readBase: noBase })
    expect(result.errors.join('\n')).toContain('src/components/**')
  })

  test('engeres include faellt durch', () => {
    setup({ config: viteConfig({ include: ['src/lib/**/*.ts'] }) })
    const result = checkIntegrity({ root, readBase: noBase })
    expect(result.errors.join('\n')).toContain('src/lib/**/*.ts')
  })

  test('Spread im exclude-Array faellt durch, auch wenn die Literale stimmen', () => {
    const config = viteConfig().replace("'src/main.{js,ts}',", "'src/main.{js,ts}', ...extraExcludes,")
    expect(config).toContain('...extraExcludes')
    setup({ config })
    const result = checkIntegrity({ root, readBase: noBase })
    expect(result.errors.join('\n')).toContain('coverage.exclude darf nur String-Literale')
  })

  test('Glob mit eckiger Klammer im Literal wird vollstaendig gelesen', () => {
    const config = viteConfig().replace("'src/main.{js,ts}',", "'src/main.{js,ts}', 'src/[ab]/**',")
    expect(config).toContain("'src/[ab]/**'")
    setup({ config })
    const result = checkIntegrity({ root, readBase: noBase })
    const text = result.errors.join('\n')
    expect(text).toContain('src/[ab]/**')
    expect(text).not.toContain('darf nur String-Literale')
  })
})

describe('Scope-Parser (Kommentare, Gueltigkeitsbereich)', () => {
  test('Zeilenende-Kommentar mit Literal wird nicht als Scope gelesen', () => {
    const config = viteConfig().replace(
      "include: ['src/**/*.{js,ts,vue}'],",
      "include: ['src/lib/**', // 'src/**/*.{js,ts,vue}'\n      ],",
    )
    expect(readActiveScope(config).include).toEqual(['src/lib/**'])
    setup({ config })
    const result = checkIntegrity({ root, readBase: noBase, allowMissingBase: true })
    // Das verengte include faellt auf, statt als Soll-Scope durchzugehen.
    expect(result.errors.join('\n')).toContain('fehlt "src/**/*.{js,ts,vue}"')
  })

  test('Apostroph im Kommentar macht das Array nicht unlesbar', () => {
    const config = viteConfig().replace("// Kommentar im Array", "// don't panic, it's fine")
    expect(readActiveScope(config).exclude).toEqual(EXCLUDE)
    setup({ config })
    expect(checkIntegrity({ root, readBase: () => baseline() }).errors).toEqual([])
  })

  test('Blockkommentar im Array wird ignoriert, auch mit Literal darin', () => {
    const config = viteConfig().replace("// Kommentar im Array", "/* 'src/phantom/**', \n 'x' */")
    expect(readActiveScope(config).exclude).toEqual(EXCLUDE)
  })

  test('Kommentarzeichen innerhalb eines Literals bleiben Teil des Literals', () => {
    const config = viteConfig().replace("'src/main.{js,ts}',", "'src/main.{js,ts}', 'src//x/**', 'a/*b*/c',")
    expect(readActiveScope(config).exclude).toEqual([...EXCLUDE, 'src//x/**', 'a/*b*/c'])
  })

  test('fehlt coverage.exclude, wird kein spaeteres Array als Scope gelesen', () => {
    const config = viteConfig().replace(/ {6}exclude: \[\n[\s\S]*?\],\n/, '') + "\nexport const other = { server: { exclude: ['src/phantom/**'] } }\n"
    expect(readActiveScope(config)).toBeNull()
    setup({ config })
    const result = checkIntegrity({ root, readBase: noBase, allowMissingBase: true })
    expect(result.errors.join('\n')).toContain('nicht lesbar')
  })

  test('test.exclude vor dem coverage-Block wird nicht mit coverage.exclude verwechselt', () => {
    const scope = readActiveScope(viteConfig())
    expect(scope.exclude).toEqual(EXCLUDE)
    expect(scope.exclude).not.toContain('node_modules/**')
  })

  test('maskSource erhaelt Laenge und Zeilenumbrueche', () => {
    const source = "a // c1\n/* c2\n c3 */ 'x\\'y' \"z\" `t\nu`\nit's\n"
    const masked = maskSource(source)
    expect(masked.length).toBe(source.length)
    expect([...masked].filter((c) => c === '\n').length).toBe([...source].filter((c) => c === '\n').length)
    expect(masked).not.toContain('c1')
    expect(masked).not.toContain('c2')
  })
})

describe('Schwellen-Quelle', () => {
  const run = (config) => {
    setup({ config })
    return checkIntegrity({ root, readBase: noBase, allowMissingBase: true }).errors.join('\n')
  }

  test('lines/branches aus der Baseline gelesen geht durch', () => {
    setup()
    expect(checkIntegrity({ root, readBase: () => baseline() }).errors).toEqual([])
  })

  test('Baseline-Datei nicht per JSON.parse geladen faellt durch', () => {
    expect(run(viteConfig().replace('coverage-baseline.json', 'other.json'))).toContain('Schwellen muessen aus coverage-baseline.json')
  })

  test('hartkodiertes lines faellt durch, auch wenn der Dateiname im Kommentar steht', () => {
    const config = viteConfig().replace('lines: coverageBaseline.line_min', 'lines: 0 /* coverage-baseline.json */')
    expect(config).toContain('coverage-baseline.json')
    expect(run(config)).toContain('coverage.thresholds.lines muss coverageBaseline.line_min sein')
  })

  test('hartkodiertes branches faellt durch', () => {
    expect(run(viteConfig().replace('branches: coverageBaseline.branch_min', 'branches: 10'))).toContain('coverage.thresholds.branches muss')
  })

  test('vertauschte Felder fallen durch', () => {
    expect(run(viteConfig().replace('lines: coverageBaseline.line_min', 'lines: coverageBaseline.branch_min'))).toContain('coverage.thresholds.lines muss')
  })

  test('fehlendes lines oder branches faellt durch', () => {
    expect(run(viteConfig().replace('lines: coverageBaseline.line_min, ', ''))).toContain('gefunden: fehlt')
  })

  test('auskommentiertes lines faellt durch', () => {
    expect(run(viteConfig().replace('lines: coverageBaseline.line_min,', '// lines: coverageBaseline.line_min,\n lines: 5,'))).toContain('gefunden: 5')
  })

  test('thresholds-Block fehlt', () => {
    expect(run(viteConfig().replace(/ {6}thresholds:.*\n/, ''))).toContain('coverage.thresholds nicht lesbar')
  })

  test('fremde Variable ohne Baseline-Bezug faellt durch', () => {
    const config = viteConfig().replaceAll('coverageBaseline', 'other').replace("JSON.parse(readFileSync('coverage-baseline.json', 'utf-8'))", "JSON.parse(readFileSync('x.json', 'utf-8'))")
    expect(run(config)).toContain('Schwellen muessen aus coverage-baseline.json')
  })
})

describe('Skip-Marker', () => {
  test('neuer Skip ohne Allowlist faellt durch', () => {
    setup({ files: { 'src/b.test.js': "it.skip('x', () => {})\n" } })
    const result = checkIntegrity({ root, readBase: noBase })
    expect(result.errors.join('\n')).toContain('src/b.test.js')
    expect(result.errors.join('\n')).toContain('it.skip')
  })

  test('erlaubter Skip geht durch', () => {
    setup({
      files: { 'src/b.test.js': "it.skip('x', () => {})\n" },
      allowlist: {
        entries: [{ file: 'src/b.test.js', kind: 'it.skip', count: 1, reason: 'Browser-API fehlt in jsdom' }],
      },
    })
    const result = checkIntegrity({ root, readBase: noBase })
    expect(result.errors).toEqual([])
  })

  test('mehr Skips als erlaubt faellt durch', () => {
    setup({
      files: { 'src/b.test.js': "it.skip('x', () => {})\nit.skip('y', () => {})\n" },
      allowlist: {
        entries: [{ file: 'src/b.test.js', kind: 'it.skip', count: 1, reason: 'eins erlaubt' }],
      },
    })
    const result = checkIntegrity({ root, readBase: noBase })
    expect(result.errors.join('\n')).toContain('src/b.test.js')
  })

  test('veralteter Allowlist-Eintrag faellt durch', () => {
    setup({
      allowlist: {
        entries: [{ file: 'src/gone.test.js', kind: 'describe.skip', count: 1, reason: 'war mal' }],
      },
    })
    const result = checkIntegrity({ root, readBase: noBase })
    expect(result.errors.join('\n')).toContain('src/gone.test.js')
  })

  test.each(['test.skip', 'describe.skip', 'it.todo', 'xit', 'xdescribe'])('%s wird erkannt', (kind) => {
    const line = kind.startsWith('x') ? `${kind}('x', () => {})\n` : `${kind}('x')\n`
    setup({ files: { 'src/c.test.js': line } })
    const result = checkIntegrity({ root, readBase: noBase })
    expect(result.errors.join('\n')).toContain(kind)
  })

  test.each(['skipIf', 'runIf'])('%s wird erkannt', (kind) => {
    const files = { 'src/c.test.js': `it.${kind}(true)('x', () => {})\n` }
    setup({ files })
    expect(checkIntegrity({ root, readBase: noBase }).errors.join('\n')).toContain(kind)
    // Der Allowlist-Schluessel ist der Marker ohne fuehrenden Punkt.
    setup({ files, allowlist: { entries: [{ file: 'src/c.test.js', kind, count: 1, reason: 'bedingt' }] } })
    expect(checkIntegrity({ root, readBase: noBase }).errors).toEqual([])
  })
})

describe('Ratchet gegen origin/main', () => {
  test('abgesenkte Schwelle faellt durch', () => {
    setup({ base: baseline({ line_min: 70 }) })
    const result = checkIntegrity({ root, readBase: () => baseline() })
    expect(result.errors.join('\n')).toContain('line_min')
  })

  test('abgesenkte Schwelle mit passender lowering_approval geht durch', () => {
    const approval = { approved_by: 'Maintainer', reason: 'Testdatei entfernt', line_min: 70 }
    setup({ base: baseline({ line_min: 70, lowering_approval: approval }) })
    const result = checkIntegrity({ root, readBase: () => baseline() })
    expect(result.errors).toEqual([])
  })

  test('lowering_approval deckt keine weitere Absenkung', () => {
    const approval = { approved_by: 'Maintainer', reason: 'Testdatei entfernt', line_min: 70 }
    setup({ base: baseline({ line_min: 60, lowering_approval: approval }) })
    const result = checkIntegrity({ root, readBase: () => baseline() })
    expect(result.errors.join('\n')).toContain('line_min')
  })

  test('weiterer Scope (neues exclude) gegenueber main faellt durch', () => {
    const wider = { include: [...INCLUDE], exclude: [...EXCLUDE, 'src/views/**'] }
    setup({
      config: viteConfig({ exclude: wider.exclude }),
      base: baseline({ scope: wider }),
    })
    const result = checkIntegrity({ root, readBase: () => baseline() })
    expect(result.errors.join('\n')).toContain('src/views/**')
  })

  test('fehlende Datei auf origin/main wird uebersprungen', () => {
    setup()
    const result = checkIntegrity({ root, readBase: noBase })
    expect(result.errors).toEqual([])
    expect(result.notes.join('\n')).toContain('origin/main')
  })
})
