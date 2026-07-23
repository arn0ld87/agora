/**
 * runModelOverride — Spec für die transiente Run-Override-Senke.
 *
 * Sichert Roundtrip, Source-Normalisierung auf 'run-override' und das
 * defensive Entsorgen korrupter/invalider sessionStorage-Einträge ab.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import {
  RUN_MODEL_OVERRIDE_KEY,
  clearRunModelOverride,
  getRunModelOverride,
  setRunModelOverride,
} from '../runModelOverride'

describe('runModelOverride (transiente Dashboard-Senke)', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  it('Roundtrip: set normalisiert source auf run-override, get liefert den Ref', () => {
    setRunModelOverride({
      provider_connection_id: 'conn-1',
      model_id: 'm-1',
      source: 'explicit',
    })
    expect(getRunModelOverride()).toEqual({
      provider_connection_id: 'conn-1',
      model_id: 'm-1',
      source: 'run-override',
    })
  })

  it('clear entfernt die Senke', () => {
    setRunModelOverride({
      provider_connection_id: 'conn-1',
      model_id: 'm-1',
      source: 'explicit',
    })
    clearRunModelOverride()
    expect(getRunModelOverride()).toBeNull()
    expect(sessionStorage.getItem(RUN_MODEL_OVERRIDE_KEY)).toBeNull()
  })

  it('korrupter JSON-Inhalt wird defensiv entsorgt', () => {
    sessionStorage.setItem(RUN_MODEL_OVERRIDE_KEY, '{not json')
    expect(getRunModelOverride()).toBeNull()
    expect(sessionStorage.getItem(RUN_MODEL_OVERRIDE_KEY)).toBeNull()
  })

  it('invalides Shape (leere model_id) wird defensiv entsorgt', () => {
    sessionStorage.setItem(
      RUN_MODEL_OVERRIDE_KEY,
      JSON.stringify({ provider_connection_id: 'conn-1', model_id: '', source: 'run-override' }),
    )
    expect(getRunModelOverride()).toBeNull()
    expect(sessionStorage.getItem(RUN_MODEL_OVERRIDE_KEY)).toBeNull()
  })

  it('set mit invalider Referenz schreibt nichts', () => {
    setRunModelOverride({
      provider_connection_id: '',
      model_id: 'm-1',
      source: 'explicit',
    })
    expect(sessionStorage.getItem(RUN_MODEL_OVERRIDE_KEY)).toBeNull()
  })
})
