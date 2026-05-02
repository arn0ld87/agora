// Issue #133 — Settings-API-Client.
//
// Schlanker Wrapper um die vier Backend-Endpunkte. ``service`` ist die
// gemeinsame Axios-Instanz mit Auth-Header und Envelope-Handling, die
// auch alle anderen API-Module nutzen.

import service from './index'

export function fetchSettings() {
  return service.get('/api/settings')
}

export function fetchSettingsSchema() {
  return service.get('/api/settings/schema')
}

export function putSettings(payload) {
  // ``payload`` = flaches { KEY: value }-Objekt. Backend lehnt
  // Secrets hier mit ``code: secret_not_allowed`` ab — die View
  // separiert sie deshalb vorher.
  return service.put('/api/settings', payload)
}

export function putSecrets(secretsPayload) {
  // Erwartet ``{ confirm: true, fields: { KEY: value, ... } }``.
  // Backend lehnt non-secret Keys symmetrisch ab.
  return service.put('/api/settings/secrets', {
    confirm: true,
    fields: secretsPayload || {},
  })
}
