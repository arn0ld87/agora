/**
 * deriveSystemTone (#1795) — Zustandspunkt der Seitenleiste.
 * Regeln spiegeln SystemHealthCard: Ollama `reachable === null` ist kein Fehler.
 */
import { describe, it, expect } from 'vitest'
import { deriveSystemTone } from '../useSidebarSystem'
import type { SystemStatusResponse } from '../../contracts/systemStatusContract'

function status(over: { backendOk?: boolean; neo4j?: boolean; ollama?: boolean | null } = {}): SystemStatusResponse {
  return {
    backend: { ok: over.backendOk ?? true },
    neo4j: { reachable: over.neo4j ?? true },
    ollama: { reachable: over.ollama === undefined ? true : over.ollama, models_available: [] },
    disk: { uploads: {} },
    timestamp: '2026-10-06T10:00:00Z',
  }
}

describe('deriveSystemTone', () => {
  it('ohne Status ist der Zustand unbekannt', () => {
    expect(deriveSystemTone(null)).toBe('unknown')
  })
  it('alles erreichbar → ok', () => {
    expect(deriveSystemTone(status())).toBe('ok')
  })
  it('Ollama-Probe uebersprungen (null) ist kein Fehler', () => {
    expect(deriveSystemTone(status({ ollama: null }))).toBe('ok')
  })
  it.each([
    ['Backend', { backendOk: false }],
    ['Neo4j', { neo4j: false }],
    ['Ollama', { ollama: false }],
  ])('%s nicht erreichbar → err', (_name, over) => {
    expect(deriveSystemTone(status(over))).toBe('err')
  })
})
