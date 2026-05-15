/**
 * useApiAuth — Composable für transparente Ticket-Auth mit Auto-Refresh.
 *
 * Smoke-Fix Welle 2, Slice 03 (P1-Befund #4):
 * Nach ~5 min Browser-Idle war POST /api/auth/ticket selbst nicht mehr
 * erreichbar, weil der abgelaufene X-Ticket-Header die Guard blockierte.
 * Der Backend-Fix (token_only_endpoints) erlaubt jetzt Re-Auth via Master-Token.
 *
 * Dieses Composable ergänzt die Frontend-Seite:
 * - fetchTicket(scope): holt Ticket mit Cache (exp-5s Vorlauf), kein Doppel-Fetch.
 * - withFreshTicket(scope, fn): ruft fn(ticket) auf, refresht bei 401 einmal.
 *
 * Keine Side-Effects auf globale Stores.
 * console.warn nur bei Refresh-Fall, kein console.log-Spam.
 */

import service from '../api/index'

// ---------------------------------------------------------------------------
// Typen
// ---------------------------------------------------------------------------

interface TicketCacheEntry {
  ticket: string
  /** Unix-Timestamp (ms) bis zu dem das Ticket als frisch gilt. */
  validUntilMs: number
}

interface TicketApiResponse {
  data?: {
    ticket?: string
    exp?: number
    scope?: string
  }
}

// ---------------------------------------------------------------------------
// Modul-Level Ticket-Cache (pro Scope)
// ---------------------------------------------------------------------------

const _cache = new Map<string, TicketCacheEntry>()

const _EARLY_EXPIRE_BUFFER_MS = 5_000 // 5 Sekunden Vorlauf vor exp

function _isCacheValid(entry: TicketCacheEntry): boolean {
  return Date.now() < entry.validUntilMs
}

function _clearCache(scope?: string): void {
  if (scope) {
    _cache.delete(scope)
  } else {
    _cache.clear()
  }
}

// ---------------------------------------------------------------------------
// fetchTicket — mit Cache
// ---------------------------------------------------------------------------

/**
 * Holt ein frisches Ticket für den gegebenen Scope.
 * Gibt ein gecachtes Ticket zurück, solange es noch (exp - 5s) Sekunden gültig ist.
 *
 * @throws Wenn der POST /api/auth/ticket nicht 200 zurückliefert.
 */
async function fetchTicket(scope: string): Promise<string> {
  const cached = _cache.get(scope)
  if (cached && _isCacheValid(cached)) {
    return cached.ticket
  }

  const res = await service.post('/api/auth/ticket', { scope, ttl_seconds: 60 })
  const body = res as unknown as TicketApiResponse
  const ticket = body?.data?.ticket
  const exp = body?.data?.exp

  if (!ticket) {
    throw new Error(`[useApiAuth] POST /api/auth/ticket returned no ticket (scope=${scope})`)
  }

  // exp ist ein Unix-Timestamp in Sekunden; Cache mit Vorlauf setzen.
  const validUntilMs =
    typeof exp === 'number'
      ? exp * 1000 - _EARLY_EXPIRE_BUFFER_MS
      : Date.now() + 55_000 // Fallback: 55s (TTL=60s minus Puffer)

  _cache.set(scope, { ticket, validUntilMs })
  return ticket
}

// ---------------------------------------------------------------------------
// withFreshTicket — mit einmaligem Retry bei 401
// ---------------------------------------------------------------------------

/** Minimale Fehlerform mit optionalem status-Feld. */
interface MaybeStatusError {
  status?: number
  response?: { status?: number }
}

function _is401(err: unknown): boolean {
  if (err == null || typeof err !== 'object') return false
  const e = err as MaybeStatusError
  return e.status === 401 || e.response?.status === 401
}

/**
 * Führt `fn(ticket)` mit einem frischen Ticket für den gegebenen Scope aus.
 * Bei 401 wird das Ticket einmalig erneuert und `fn` erneut aufgerufen.
 * Bei zweitem 401 wird der Fehler propagiert.
 *
 * @param scope  Ticket-Scope, z.B. `"sse:sim_abc"` oder `"llm-stream"`.
 * @param fn     Async-Funktion, die das Ticket als Parameter erhält.
 */
async function withFreshTicket<T>(
  scope: string,
  fn: (ticket: string) => Promise<T>
): Promise<T> {
  const ticket = await fetchTicket(scope)
  try {
    return await fn(ticket)
  } catch (err: unknown) {
    if (!_is401(err)) throw err

    // Einmaliger Refresh: Cache invalidieren und neu holen.
    console.warn(`[useApiAuth] 401 on scope="${scope}", refreshing ticket once.`)
    _clearCache(scope)

    const freshTicket = await fetchTicket(scope)
    return await fn(freshTicket)
  }
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export const useApiAuth = {
  fetchTicket,
  withFreshTicket,
  /** Testhelfer: Cache manuell leeren. */
  _clearCache,
}

export type { TicketCacheEntry }
