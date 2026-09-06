/**
 * useSimulationLiveMetrics — reine Ableitungsfunktionen fuer die Live-
 * Instrument-Kopfzeile und die Rundenachse (PR 7, Redesign-Serie 2026-09).
 *
 * Bewusst zustandslos: die View haelt die Quellzustaende (runStatus, Posts,
 * Sim-Uhr), diese Datei rechnet nur um. Das macht die Ableitung ohne Mount
 * testbar (kein Router/i18n/EventSource-Setup noetig).
 *
 * Namenshinweis: eine gleichnamige Datei `useDeriveSimulation.ts` existierte
 * bereits (Block B4, Dossier — "Lauf aus Bericht ableiten") mit voellig
 * anderer Bedeutung. Dieses Modul heisst deshalb bewusst anders, statt die
 * bestehende Datei zu ueberschreiben.
 *
 * Datenherkunft (siehe Audit §5 "Simulation live"):
 * - currentRound/totalRounds: RunStatusResponse (bestehender
 *   /api/simulation/status[-detail]-Endpunkt, s. api/simulation.ts)
 * - Posts fuer die Akteurs-Bahn: PostCreatedEvent-Strom (useSimFeed, bereits
 *   Zod-validiert)
 * - elapsedSec: useSimClock (Sim-Uhr aus PostCreatedEvent.sim_time)
 *
 * Nicht abgeleitet (bewusst weggelassen, siehe PR-7-Bericht):
 * - Rundenachse "Hoehe = Beitraege je Runde": PostCreatedEvent traegt kein
 *   round_num-Feld; eine Beitragszahl pro Runde ist aus den erlaubten,
 *   bereits validierten Quellen nicht ableitbar. Die Achse markiert daher
 *   nur den Rundenstatus (erledigt/jetzt/geplant), keine Aktivitaetshoehe.
 * - "Aufkommende Themen": kein Themen-Extraktions-Endpunkt vorhanden.
 */

import type { PostCreatedEvent } from '@/contracts/postEventContract'

export type RoundTickState = 'done' | 'now' | 'todo'

export interface RoundTick {
  round: number
  state: RoundTickState
}

/**
 * Baut die Rundenachse: eine Markierung pro Runde 1..totalRounds.
 * `currentRound <= 0` oder `totalRounds <= 0` liefert eine leere Achse
 * (noch kein Lauf gestartet / keine Daten).
 */
export function buildRoundTicks(currentRound: number, totalRounds: number): RoundTick[] {
  if (totalRounds <= 0) return []
  const ticks: RoundTick[] = []
  for (let round = 1; round <= totalRounds; round += 1) {
    let state: RoundTickState = 'todo'
    if (round < currentRound) state = 'done'
    else if (round === currentRound) state = 'now'
    ticks.push({ round, state })
  }
  return ticks
}

/** s/Runde — Sekunden im Sim-Lauf geteilt durch die bereits gelaufenen
 * Runden. `null` wenn noch keine volle Runde vorliegt (Division ohne
 * Aussagekraft). */
export function secondsPerRound(elapsedSec: number, currentRound: number): number | null {
  if (currentRound <= 0 || elapsedSec <= 0) return null
  return elapsedSec / currentRound
}

export interface ActorStat {
  personaId: string
  personaName: string
  count: number
  /** true wenn die Persona innerhalb des `recentWindow`-Fensters (jüngste
   * Posts in Eingangsreihenfolge) zuletzt aktiv war. */
  isActive: boolean
}

/**
 * Gruppiert den Post-Strom (Reddit + Twitter kombiniert) nach persona_id.
 * Sortiert nach Beitragszahl absteigend — die aktivsten Akteure zuerst,
 * analog der Zielvorlage (simulation-live.html, Akteure-Bahn).
 */
export function buildActorStats(
  posts: readonly PostCreatedEvent[],
  recentWindow = 10,
): ActorStat[] {
  const byId = new Map<string, ActorStat>()
  for (const post of posts) {
    const existing = byId.get(post.persona_id)
    if (existing) {
      existing.count += 1
    } else {
      byId.set(post.persona_id, {
        personaId: post.persona_id,
        personaName: post.persona_name,
        count: 1,
        isActive: false,
      })
    }
  }
  const recentIds = new Set(posts.slice(-recentWindow).map((p) => p.persona_id))
  for (const id of recentIds) {
    const stat = byId.get(id)
    if (stat) stat.isActive = true
  }
  return [...byId.values()].sort((a, b) => b.count - a.count)
}

/** Formatiert Sekunden als `mm:ss` bzw. `hh:mm:ss` ab einer Stunde. */
export function formatElapsed(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n: number): string => String(n).padStart(2, '0')
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

/** Formatiert s/Runde auf eine Nachkommastelle, `—` wenn nicht ableitbar. */
export function formatSecondsPerRound(value: number | null): string {
  if (value === null) return '—'
  return `${value.toFixed(1)} s`
}
