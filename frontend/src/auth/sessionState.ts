/**
 * sessionState — kleines Singleton, das den aktuellen Supabase-Access-Token
 * und die aktive Workspace-ID hält.
 *
 * Zweck: Verhindert einen zirkulären Import zwischen `src/api/index.ts` und
 * `src/store/auth.ts`, indem `authHeaders()` nur dieses Modul liest (ohne
 * den ganzen Pinia-Store importieren zu müssen).
 *
 * Der Auth-Store schreibt hier; `authHeaders()` liest nur.
 * Niemals Tokens in Logs ausgeben.
 */

let _accessToken: string | null = null
let _workspaceId: string | null = null

export function setSessionToken(token: string | null): void {
  _accessToken = token
}

export function getSessionToken(): string | null {
  return _accessToken
}

export function setActiveWorkspaceId(id: string | null): void {
  _workspaceId = id
}

export function getActiveWorkspaceId(): string | null {
  return _workspaceId
}
