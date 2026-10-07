import type {
  LocationQuery,
  NavigationGuardReturn,
  RouteLocationAsRelativeGeneric,
  RouteLocationNormalized,
  RouteLocationRaw,
} from 'vue-router'

/**
 * Weiterleitungen alter Adressen auf die Etappe-2-Ziele (Frontend-Umbau,
 * Bauplan §6.2, Spalte „ab Etappe“ = 2). Die alten Routen-Namen bleiben als
 * Weiterleitungs-Routen bestehen, damit kein `router.push({ name })` bricht.
 *
 * Query und Hash des alten Aufrufs bleiben erhalten (vue-router uebernimmt sie,
 * sofern das Ziel sie nicht selbst setzt); nur der Ablage-Filter entfaellt,
 * weil er am Ziel in den Pfad oder in `?view=` uebergeht.
 */

/** Query ohne den Ablage-Filter; die uebrigen Schluessel bleiben stehen. */
function withoutFilter(query: LocationQuery): LocationQuery {
  const rest: LocationQuery = { ...query }
  delete rest.filter
  return rest
}

/**
 * `/ablage?filter=…` → Bibliothek bzw. Aktivitaet.
 * Personasaetze haben bis Etappe 7 keine eigene Ansicht und fuehren auf die Laeufe.
 */
export function shelfRedirect(to: { query: LocationQuery }): RouteLocationAsRelativeGeneric {
  const filter = typeof to.query.filter === 'string' ? to.query.filter : ''
  const query = withoutFilter(to.query)
  switch (filter) {
    case 'bericht':
      return { name: 'LibraryRuns', query: { ...query, view: 'with-report' } }
    case 'graph':
      return { name: 'LibraryGraphs', query }
    case 'jobs':
      return { name: 'ActivityJobs', query }
    default:
      // alle, lauf, personasatz (bis Etappe 7) und unbekannte Werte
      return { name: 'LibraryRuns', query }
  }
}

/**
 * Welche Kennung die Ablage fuer einen Lauf fuehrt: den Vorhaben-Schluessel
 * `endeavorKey` (useShelf), also die `simulation_id`, ersatzweise die
 * `project_id`, ersatzweise die `run_id`. Nur eine `sim_`-Kennung ist ein
 * Lauf-Arbeitsbereich; die anderen beiden gehen an ihre eigene Ansicht.
 */
function laufTarget(id: string, carry: { query: LocationQuery; hash: string }): RouteLocationRaw {
  if (id.startsWith('sim_')) return { name: 'RunOverview', params: { simulationId: id }, ...carry }
  if (id.startsWith('proj_')) return { name: 'GraphLibraryDetail', params: { projectId: id }, ...carry }
  return { name: 'ActivityJobDetail', params: { runId: id }, ...carry }
}

/**
 * `beforeEnter` der Objekt-Route `/ablage/:kind/:objectId`. Lauf, Graph und
 * Bericht werden umgeleitet (der Bericht auf `/v4/report/:id`, das den Lauf aus
 * dem Bericht aufloest, Etappe 5); der Personasatz bleibt bis Etappe 7 auf der
 * alten Ablage-Ansicht (Bauplan §6.2).
 */
export function shelfObjectGuard(to: RouteLocationNormalized): NavigationGuardReturn {
  const id = String(to.params.objectId)
  const carry = { query: to.query, hash: to.hash }
  if (to.params.kind === 'lauf') return laufTarget(id, carry)
  if (to.params.kind === 'bericht') return { name: 'StepReport', params: { reportId: id }, ...carry }
  if (to.params.kind === 'graph') {
    return { name: 'GraphLibraryDetail', params: { projectId: id }, ...carry }
  }
  return true
}

/**
 * Etappe 4 (#1801, Bauplan §6.2): die Simulations-Adressen unter
 * `/v4/simulation/:id/…` leiten auf die Unterreiter am Lauf um. Query und Hash
 * bleiben erhalten; `postId` (mit Doppelpunkten) wird unveraendert uebernommen.
 */
/** Das Minimum, das die Weiterleitungen aus dem Ziel lesen. */
interface RedirectSource {
  params: RouteLocationNormalized['params']
  query: LocationQuery
  hash: string
}

function simulationCarry(to: RedirectSource) {
  return { params: { simulationId: String(to.params.simulationId) }, query: to.query, hash: to.hash }
}

export function simulationFeedRedirect(to: RedirectSource): RouteLocationAsRelativeGeneric {
  return { name: 'RunSimulationFeed', ...simulationCarry(to) }
}

export function simulationPostRedirect(to: RedirectSource): RouteLocationAsRelativeGeneric {
  const { params, ...rest } = simulationCarry(to)
  return { name: 'RunSimulationPost', params: { ...params, postId: String(to.params.postId) }, ...rest }
}

export function simulationRoundsRedirect(to: RedirectSource): RouteLocationAsRelativeGeneric {
  return { name: 'RunSimulationRounds', ...simulationCarry(to) }
}
