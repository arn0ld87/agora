/**
 * Objektmodell der Ablage (Block B3, „Richtung B · Dossier“).
 *
 * Vokabular verbindlich aus CONTEXT.md → Glossar:
 *   Lauf        — das ganze Vorhaben, eine Zeile in der Ablage
 *   Job         — ein Einzelschritt (RunRegistry, run_type) — nur im
 *                 Filter „Alle Jobs“ sichtbar, nie Standardansicht
 *   Bericht     — Leseergebnis, eigenes Objekt
 *   Personasatz — wiederverwendbare Personasammlung, eigenes Objekt
 *   Graph       — Quellenumfeld, eigenes Objekt
 *
 * Die Ablage sortiert chronologisch: zuletzt angefasst zuerst.
 */

export type ShelfObjectKind = 'lauf' | 'bericht' | 'personasatz' | 'graph'

/** Kurzlabel in der Zeile (Entwurf: LAUF / BER / PERS / GRPH). */
export const SHELF_KIND_TAG: Record<ShelfObjectKind, string> = {
  lauf: 'LAUF',
  bericht: 'BER',
  personasatz: 'PERS',
  graph: 'GRPH',
}

/**
 * Die Weiter-Aktion (aus Richtung C): jede Zeile sagt, was als
 * Naechstes zu tun ist — „9 Befunde pruefen“, „Personas freigeben“,
 * „Zusehen“. `to` ist ein Router-Ziel; `kind` steuert die Betonung
 * (accent = normale Fortsetzung, warn = blockiert/Handlung noetig).
 */
export interface NextAction {
  label: string
  to: { name: string; params?: Record<string, string> }
  kind: 'accent' | 'warn' | 'neutral'
}

export interface ShelfObject {
  kind: ShelfObjectKind
  /** Primaerschluessel des Objekts (sim_/report_/proj_/template-id). */
  id: string
  title: string
  /**
   * Statuszeile unter dem Titel — nennt Zustand ALS TEXT, nicht nur
   * als Farbe (Systemregel des Entwurfs): „Simulation pausiert ·
   * Runde 12/20", „9 Red-Team-Befunde offen“.
   */
  statusLine: string
  /** Meta-Zeile: Zeitpunkt + technische ID (Geist Mono). */
  updatedAt: string
  metaId: string
  /** Nur bei kind='bericht': die Simulation, aus der er stammt — Grundlage fuers Ableiten. */
  simulationId?: string | null
  /** Nur bei kind='graph': die Graph-ID des Projekts, fuer das Nachladen im Dossier. */
  graphId?: string | null
  nextAction: NextAction | null
  /**
   * Laufende Aktivitaet: traegt die Zeilenaktionen Abbrechen/Pause
   * und den globalen Topbar-Indikator. runId ist die Job-ID der
   * RunRegistry (run_), die der Cancel-Endpoint versteht — er loest
   * auch sim_-IDs auf, aber die Zeile soll nicht raten muessen.
   */
  active: {
    runId: string
    /** Job-Status aus dem Contract (pending|processing|paused). */
    status: 'pending' | 'processing' | 'paused'
    /** Pause/Resume gibt es nur fuer laufende Simulationen (Q21). */
    pausable: boolean
    simulationId: string | null
    /** Fortschritt 0-100 aus dem Contract (RunDetail.progress), fuer die Uebersicht (Block B3). */
    progress: number | null
  } | null
}

/** Filterleiste der Ablage (Entwurf: Alle 24 · Laeufe 9 · …). */
export type ShelfFilter = 'alle' | ShelfObjectKind | 'jobs'

/**
 * Rohebene fuer den Filter „Alle Jobs“ (Q19c): ein Registry-Eintrag,
 * unaggregiert. Bewusst schmal — die Detailansicht ist das Dossier
 * des zugehoerigen Laufs, nicht eine eigene Job-Seite.
 */
export interface ShelfJobRow {
  runId: string
  runType: string
  status: string
  message: string
  updatedAt: string
  progress: number
}
