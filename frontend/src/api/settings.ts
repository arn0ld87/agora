// Issue #133 — Settings-API-Client.
//
// Schlanker Wrapper um die vier Backend-Endpunkte. ``service`` ist die
// gemeinsame Axios-Instanz mit Auth-Header und Envelope-Handling, die
// auch alle anderen API-Module nutzen.

import service from './index'

export interface SettingsResponse {
  settings: Record<string, unknown>
  [key: string]: unknown
}

export interface SettingsSchemaResponse {
  schema: Record<string, unknown>
  [key: string]: unknown
}

export type SecretsPayload = Record<string, string>

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
