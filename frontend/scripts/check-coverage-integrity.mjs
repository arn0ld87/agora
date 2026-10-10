#!/usr/bin/env node
// Coverage-Integritaet fuer das Frontend (Issue #1672), Gegenstueck zu
// backend/scripts/check_coverage.py --integrity. Kein Coverage-Lauf noetig.
//
// Prueft:
//  1. Aktiver Scope (coverage.include/exclude in vite.config.js) == Soll-Scope
//     in coverage-baseline.json; die Schwellen kommen aus der Baseline-Datei.
//  2. Skip-Marker in src/ und tests/ nur mit Eintrag in coverage-skip-allowlist.json
//     (Datei, Art, Anzahl); veraltete Eintraege sind ebenfalls ein Fehler.
//  3. Ratchet gegen origin/main:frontend/coverage-baseline.json: line_min/branch_min
//     sinken nicht, der Scope wird nicht weiter. Existiert die Datei dort nicht
//     (Erstanlage), wird der Teil mit Hinweis uebersprungen.
//
// Aufruf: bun scripts/check-coverage-integrity.mjs   (aus frontend/)

import { execFileSync } from 'node:child_process'
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const BASE_REF = 'origin/main'
const BASELINE_FILE = 'coverage-baseline.json'
const ALLOWLIST_FILE = 'coverage-skip-allowlist.json'
const CONFIG_FILE = 'vite.config.js'
const SCAN_DIRS = ['src', 'tests']
const SKIP_DIRS = new Set(['node_modules', 'dist', 'coverage'])
const SCAN_EXT = /\.(?:[cm]?[jt]s|vue)$/

// Reihenfolge zaehlt: spezifische Muster zuerst, jede Fundstelle nur einmal.
const SKIP_PATTERNS = [
  /\b(?:it|test|describe)\.(?:skip|todo)\b/g,
  /\bx(?:it|test|describe)(?=\s*\()/g,
  /\.(?:skipIf|runIf)\b/g,
]

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf-8'))
}

function stringLiterals(text) {
  const out = []
  for (const match of text.matchAll(/'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"/g)) {
    out.push(match[1] ?? match[2])
  }
  return out
}

function arrayAfter(source, key) {
  const keyMatch = new RegExp(`\\b${key}\\s*:\\s*\\[`).exec(source)
  if (!keyMatch) return null
  const start = keyMatch.index + keyMatch[0].length
  const end = source.indexOf(']', start)
  if (end === -1) return null
  const body = source
    .slice(start, end)
    .split('\n')
    .map((line) => line.replace(/^\s*\/\/.*$/, ''))
    .join('\n')
  return stringLiterals(body)
}

/** Liest coverage.include/exclude aus dem Quelltext der Vite-Konfiguration. */
export function readActiveScope(configSource) {
  const marker = /\bcoverage\s*:\s*\{/.exec(configSource)
  if (!marker) return null
  const tail = configSource.slice(marker.index + marker[0].length)
  const include = arrayAfter(tail, 'include')
  const exclude = arrayAfter(tail, 'exclude')
  if (!include || !exclude) return null
  return { include, exclude }
}

const sorted = (items) => [...items].sort()

function checkScope(configSource, baseline) {
  const errors = []
  const active = readActiveScope(configSource)
  if (!active) {
    return [`${CONFIG_FILE}: coverage.include/exclude nicht lesbar (Block "coverage: { ... }" fehlt)`]
  }
  if (!configSource.includes(BASELINE_FILE)) {
    errors.push(`${CONFIG_FILE}: Schwellen muessen aus ${BASELINE_FILE} gelesen werden (Verweis fehlt)`)
  }
  const wanted = baseline.scope ?? { include: [], exclude: [] }
  for (const key of ['include', 'exclude']) {
    const have = new Set(active[key])
    const want = new Set(wanted[key])
    for (const item of have) {
      if (!want.has(item)) {
        errors.push(`${CONFIG_FILE}: coverage.${key} enthaelt "${item}", das nicht im Soll-Scope von ${BASELINE_FILE} steht`)
      }
    }
    for (const item of want) {
      if (!have.has(item)) {
        errors.push(`${CONFIG_FILE}: coverage.${key} fehlt "${item}" aus dem Soll-Scope von ${BASELINE_FILE}`)
      }
    }
  }
  return errors
}

function* walk(dir) {
  if (!existsSync(dir)) return
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue
    const full = join(dir, name)
    if (statSync(full).isDirectory()) yield* walk(full)
    else if (SCAN_EXT.test(name)) yield full
  }
}

function countSkips(root) {
  const counts = new Map() // "datei\u0000art" -> Anzahl
  for (const dir of SCAN_DIRS) {
    for (const file of walk(join(root, dir))) {
      const rel = relative(root, file).split(sep).join('/')
      const text = readFileSync(file, 'utf-8')
      const taken = []
      for (const pattern of SKIP_PATTERNS) {
        for (const match of text.matchAll(pattern)) {
          const from = match.index
          const to = from + match[0].length
          if (taken.some(([a, b]) => from < b && to > a)) continue
          taken.push([from, to])
          const key = `${rel}\u0000${match[0]}`
          counts.set(key, (counts.get(key) ?? 0) + 1)
        }
      }
    }
  }
  return counts
}

function checkSkips(root) {
  const errors = []
  const allowPath = join(root, ALLOWLIST_FILE)
  const entries = existsSync(allowPath) ? (readJson(allowPath).entries ?? []) : []
  const allowed = new Map()
  for (const entry of entries) {
    if (!String(entry.reason ?? '').trim()) {
      errors.push(`${ALLOWLIST_FILE}: Eintrag ${entry.file} (${entry.kind}) ohne Begruendung`)
    }
    allowed.set(`${entry.file}\u0000${entry.kind}`, entry.count)
  }
  const found = countSkips(root)
  for (const [key, count] of found) {
    const [file, kind] = key.split('\u0000')
    const limit = allowed.get(key)
    if (limit === undefined) {
      errors.push(`${file}: ${count}x ${kind} ohne Eintrag in ${ALLOWLIST_FILE}`)
    } else if (count !== limit) {
      errors.push(`${file}: ${count}x ${kind}, Allowlist erlaubt ${limit} (Eintrag anpassen oder Skip entfernen)`)
    }
  }
  for (const [key, limit] of allowed) {
    if (!found.has(key)) {
      const [file, kind] = key.split('\u0000')
      errors.push(`${ALLOWLIST_FILE}: veralteter Eintrag ${file} (${kind}, ${limit}x), Marker nicht mehr vorhanden`)
    }
  }
  return errors
}

function checkRatchet(current, base, notes) {
  const errors = []
  const approval = current.lowering_approval ?? {}
  const approved =
    typeof approval === 'object' &&
    ['approved_by', 'reason'].every((field) => String(approval[field] ?? '').trim())
  for (const key of ['line_min', 'branch_min']) {
    const value = Number(current[key])
    const floor = Number(base[key])
    if (value >= floor) continue
    const approvedValue = approved ? approval[key] : undefined
    if (typeof approvedValue === 'number' && value >= approvedValue) {
      notes.push(`${key} ${value.toFixed(2)} < ${floor.toFixed(2)} (${BASE_REF}), freigegeben von ${approval.approved_by}: ${approval.reason}`)
      continue
    }
    errors.push(
      `${BASELINE_FILE}: ${key} ${value.toFixed(2)} < ${floor.toFixed(2)} (${BASE_REF}) ohne passende lowering_approval (approved_by, reason, ${key} >= ${value.toFixed(2)})`,
    )
  }
  const baseScope = base.scope ?? { include: [], exclude: [] }
  const curScope = current.scope ?? { include: [], exclude: [] }
  const curInclude = new Set(curScope.include)
  const baseExclude = new Set(baseScope.exclude)
  for (const item of baseScope.include) {
    if (!curInclude.has(item)) {
      errors.push(`${BASELINE_FILE}: scope.include verengt, "${item}" von ${BASE_REF} fehlt`)
    }
  }
  for (const item of curScope.exclude) {
    if (!baseExclude.has(item)) {
      errors.push(`${BASELINE_FILE}: scope.exclude erweitert um "${item}" gegenueber ${BASE_REF}`)
    }
  }
  return errors
}

/** Liest die Baseline von origin/main; null, wenn die Datei dort fehlt. */
export function readBaseFromGit(root) {
  try {
    execFileSync('git', ['rev-parse', '--verify', '--quiet', `${BASE_REF}^{commit}`], { cwd: root, stdio: 'ignore' })
  } catch {
    throw new Error(`Referenz ${BASE_REF} nicht verfuegbar (git fetch origin main ausfuehren)`)
  }
  try {
    const out = execFileSync('git', ['show', `${BASE_REF}:./${BASELINE_FILE}`], {
      cwd: root,
      stdio: ['ignore', 'pipe', 'ignore'],
    })
    return JSON.parse(out.toString('utf-8'))
  } catch {
    return null
  }
}

export function checkIntegrity({ root, readBase = () => readBaseFromGit(root) }) {
  const errors = []
  const notes = []
  const baseline = readJson(join(root, BASELINE_FILE))
  errors.push(...checkScope(readFileSync(join(root, CONFIG_FILE), 'utf-8'), baseline))
  errors.push(...checkSkips(root))
  let base
  try {
    base = readBase()
  } catch (error) {
    errors.push(`Ratchet: ${error.message}`)
    return { errors, notes }
  }
  if (base) {
    errors.push(...checkRatchet(baseline, base, notes))
  } else {
    notes.push(`Ratchet uebersprungen: ${BASELINE_FILE} existiert auf ${BASE_REF} noch nicht (Erstanlage)`)
  }
  return { errors, notes }
}

function main() {
  const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
  const { errors, notes } = checkIntegrity({ root })
  for (const note of notes) console.log(`Hinweis: ${note}`)
  if (errors.length > 0) {
    console.error('Coverage-Integritaet verletzt:')
    for (const error of errors) console.error(`  - ${error}`)
    process.exit(1)
  }
  console.log('Coverage-Integritaet ok (Scope, Skip-Marker, Ratchet).')
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main()
