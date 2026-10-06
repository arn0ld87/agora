import { computed, onMounted, onUnmounted, type ComputedRef } from 'vue'
import type { SystemStatusResponse } from '../contracts/systemStatusContract'
import { useSystemStatus } from './useSystemStatus'

/**
 * Systemzustand fuer den Punkt in der Seitenleiste (#1795).
 *
 * Quelle ist dieselbe wie bei der Systemzustands-Anzeige des Dashboards
 * (`GET /api/status` ueber `useSystemStatus`). Die Regeln spiegeln
 * `SystemHealthCard`: Neo4j und Backend muessen erreichbar sein; bei Ollama
 * ist `reachable === null` (Probe uebersprungen) KEIN Fehler.
 */
export type SystemTone = 'ok' | 'err' | 'unknown'

export const SYSTEM_POLL_MS = 30_000

export function deriveSystemTone(status: SystemStatusResponse | null): SystemTone {
  if (!status) return 'unknown'
  const healthy = status.backend.ok && status.neo4j.reachable && status.ollama.reachable !== false
  return healthy ? 'ok' : 'err'
}

export function useSidebarSystem(): { tone: ComputedRef<SystemTone> } {
  const system = useSystemStatus(SYSTEM_POLL_MS)
  onMounted(() => void system.start())
  onUnmounted(() => system.stop())
  // useSystemStatus behaelt nach einem Fehler den letzten guten Stand. Der waere
  // dann veraltet: bei einem Fehler zeigt der Punkt „unbekannt“, nicht das alte Gruen.
  const tone = computed(() => (system.error.value ? 'unknown' : deriveSystemTone(system.status.value)))
  return { tone }
}
