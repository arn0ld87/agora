/**
 * Guard: API-Funktionen muessen deklarieren, was sie wirklich liefern.
 *
 * Der Response-Interceptor (`src/api/index.ts`) gibt grundsaetzlich die
 * Envelope zurueck — `{ success, data, … }` —, nicht deren `data`. Wer
 * trotzdem den ausgepackten Nutzdatentyp deklariert, luegt das
 * Typsystem an, und der Compiler kann den Aufrufer nicht mehr warnen.
 *
 * Das war kein theoretisches Problem: `listPersonaTemplates` war als
 * `Promise<PersonaTemplateRecord[]>` deklariert, ein Aufrufer griff
 * daraufhin auf `.templates` statt `.data.templates` zu — die
 * Personasaetze waeren in der Ablage nie erschienen. Und `CompareView`
 * rief `.map()` direkt auf der Envelope auf, was jedes Mal in den
 * catch-Zweig lief: die Vergleichsansicht konnte noch nie Branches
 * laden. Beide Male war der zugehoerige Test gruen, weil er dieselbe
 * falsche Annahme mockte.
 *
 * Dieser Guard liest die Quelltexte statt die Laufzeit: er findet jede
 * exportierte Funktion, die ein `service.*`-Ergebnis zurueckgibt, und
 * verlangt einen Envelope-Typ — oder einen Eintrag in der Liste der
 * bewusst flachen Endpunkte samt Backend-Beleg.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

const API_DIR = join(import.meta.dirname, '..')

/**
 * Endpunkte, die NICHT die Standard-Envelope liefern. Jeder Eintrag
 * braucht einen Beleg im Backend — wer hier etwas eintraegt, muss die
 * Route nachgesehen haben.
 */
const FLACHE_ENDPUNKTE: Record<string, string> = {
  // backend/app/api/runs.py — 202 mit {"success", "status", "run_id"},
  // ohne data-Huelle.
  cancelRun: 'runs.py::cancel_run',
  // backend/app/api/runs.py — jsonify({"run_id", "status"}), flach.
  replayRun: 'runs.py::replay_run',
  // liefert einen Blob (responseType: 'blob'), keine JSON-Huelle.
  exportRun: 'runs.py::export_run',
  fetchReportCsv: 'report.py::export_report_csv',
  fetchReportBundle: 'report.py::export_report_bundle',
  exportReport: 'report.py::export_report',
}

interface Fund {
  datei: string
  fn: string
  typ: string
}

function sammleVerstoesse(): Fund[] {
  const funde: Fund[] = []
  // Signatur bis zum Rumpfbeginn — bewusst NICHT ueber Zeilen hinweg
  // gierig, sonst faengt das Muster Kommentare und Nachbarfunktionen ein.
  const muster = /export (?:const|function) (\w+)[^=;]*?:\s*Promise<((?:[^<>]|<(?:[^<>]|<[^<>]*>)*>)*)>\s*(=>)?\s*\{?/g

  for (const datei of readdirSync(API_DIR).filter((f) => f.endsWith('.ts'))) {
    const quelle = readFileSync(join(API_DIR, datei), 'utf-8')
    for (const treffer of quelle.matchAll(muster)) {
      const [ganzer, fn, typ] = treffer
      if (fn in FLACHE_ENDPUNKTE) continue

      const rumpf = quelle.slice(treffer.index! + ganzer.length, treffer.index! + ganzer.length + 400)
      // Nur Funktionen, die das Ergebnis DIREKT durchreichen. Wer die
      // Envelope selbst auspackt und etwas anderes zurueckgibt (z.B.
      // getSimulationFeedSnapshot), beschreibt mit seinem Typ korrekt
      // die eigene Rueckgabe — das ist eine Abstraktion, kein Fehler.
      const reichtDurch = /^\s*(return\s+)?service\.(get|post|put|patch|delete)\(/.test(rumpf)
      if (!reichtDurch) continue

      const t = typ.trim()
      // ApiEnvelope/ApiResponse sind die gemeinsamen Huellen; einzelne
      // Module fuehren eigene, gleichwertige (LogEnvelope, …).
      if (/^(ApiEnvelope|ApiResponse|Blob)\b/.test(t) || /Envelope(<.*>)?$/.test(t)) continue
      funde.push({ datei, fn, typ: t })
    }
  }
  return funde
}

describe('API-Kontrakt: deklarierter Typ passt zur Envelope', () => {
  it('keine exportierte API-Funktion gibt einen ausgepackten Typ vor', () => {
    const funde = sammleVerstoesse()
    const meldung = funde
      .map((f) => `  ${f.datei}: ${f.fn} -> Promise<${f.typ}>`)
      .join('\n')

    expect(
      funde,
      funde.length === 0
        ? ''
        : `Diese Funktionen deklarieren den ausgepackten Nutzdatentyp, obwohl der\n` +
          `Interceptor die Envelope zurueckgibt:\n${meldung}\n\n` +
          `Entweder den Typ auf ApiEnvelope<T> ziehen, oder — wenn der Endpunkt\n` +
          `wirklich flach antwortet — in FLACHE_ENDPUNKTE eintragen, MIT Beleg\n` +
          `aus dem Backend (Datei::Funktion).`,
    ).toEqual([])
  })

  it('die Ausnahmeliste nennt fuer jeden Eintrag einen Backend-Beleg', () => {
    for (const [fn, beleg] of Object.entries(FLACHE_ENDPUNKTE)) {
      expect(beleg, `${fn} braucht einen Beleg der Form datei.py::funktion`).toMatch(
        /^[\w-]+\.py::\w+$/,
      )
    }
  })
})
