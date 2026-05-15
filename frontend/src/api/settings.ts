// Issue #133 — Settings-API-Client.
//
// Schlanker Wrapper um die vier Backend-Endpunkte. ``service`` ist die
// gemeinsame Axios-Instanz mit Auth-Header und Envelope-Handling, die
// auch alle anderen API-Module nutzen.

import service, { getAgoraToken } from './index'
import { useApiAuth } from '../composables/useApiAuth'

export interface SettingsResponse {
  settings: Record<string, unknown>
  [key: string]: unknown
}

export interface SettingsSchemaResponse {
  schema: Record<string, unknown>
  [key: string]: unknown
}

export type SecretsPayload = Record<string, string>

export interface SettingsStreamHandlers {
  changed?: (payload: unknown) => void
  hello?: (payload: unknown) => void
  ping?: (payload: unknown) => void
  error?: (event: Event) => void
}

export function fetchSettings(): Promise<SettingsResponse> {
  return service.get('/api/settings')
}

export function fetchSettingsSchema(): Promise<SettingsSchemaResponse> {
  return service.get('/api/settings/schema')
}

export function putSettings(
  payload: Record<string, unknown>
): Promise<SettingsResponse> {
  // ``payload`` = flaches { KEY: value }-Objekt. Backend lehnt
  // Secrets hier mit ``code: secret_not_allowed`` ab — die View
  // separiert sie deshalb vorher.
  return service.put('/api/settings', payload)
}

export function putSecrets(
  secretsPayload: SecretsPayload | null | undefined
): Promise<SettingsResponse> {
  // Erwartet ``{ confirm: true, fields: { KEY: value, ... } }``.
  // Backend lehnt non-secret Keys symmetrisch ab.
  return service.put('/api/settings/secrets', {
    confirm: true,
    fields: secretsPayload || {},
  })
}

export async function buildSettingsStreamUrl(): Promise<string> {
  const base = import.meta.env.VITE_API_BASE_URL || ''
  const path = `${base}/api/settings/stream`
  if (!getAgoraToken()) return path
  try {
    const ticket = await useApiAuth.fetchTicket('settings-stream')
    return ticket ? `${path}?ticket=${encodeURIComponent(ticket)}` : path
  } catch {
    return path
  }
}

export async function openSettingsStream(
  handlers: SettingsStreamHandlers = {}
): Promise<EventSource> {
  const url = await buildSettingsStreamUrl()
  const source = new EventSource(url)

  const namedEvents = ['settings.changed', 'hello', 'ping'] as const
  for (const name of namedEvents) {
    const mappedName = name === 'settings.changed' ? 'changed' : name
    const handler = handlers[mappedName]
    if (typeof handler === 'function') {
      source.addEventListener(name, (ev: MessageEvent) => {
        try {
          ;(handler as (payload: unknown) => void)(JSON.parse(ev.data as string))
        } catch (err) {
          console.warn(`[settings-stream] dropped malformed ${name} event`, err)
        }
      })
    }
  }

  if (typeof handlers.error === 'function') {
    source.onerror = handlers.error
  }

  return source
}
