// Tests fuer check-coverage-integrity.mjs (Issue #1672).
// Runner: bun:test, immer mit explizitem Pfad aufrufen
//   bun test ./scripts/check-coverage-integrity.test.mjs
// (Vitest sammelt scripts/ nicht ein: test.include deckt nur src/ und tests/ ab.)
import { afterEach, beforeEach, describe, expect, test } from 'bun:test'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'

import { checkIntegrity } from './check-coverage-integrity.mjs'

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
      thresholds: { lines: coverageBaseline.line_min },
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
})

describe('Schwellen-Quelle', () => {
  test('hartkodierte Schwellen statt coverage-baseline.json fallen durch', () => {
    setup({ config: viteConfig().replace('coverage-baseline.json', 'other.json') })
    const result = checkIntegrity({ root, readBase: noBase })
    expect(result.errors.join('\n')).toContain('coverage-baseline.json')
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
    setup({ files: { 'src/c.test.js': `it.${kind}(true)('x', () => {})\n` } })
    const result = checkIntegrity({ root, readBase: noBase })
    expect(result.errors.join('\n')).toContain(kind)
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
