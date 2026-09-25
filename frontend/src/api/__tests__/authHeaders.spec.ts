/**
 * authHeaders() — unit tests per auth mode.
 *
 * Modes tested:
 *  1. Legacy token only → X-Agora-Token header; no Authorization.
 *  2. Supabase session + workspace → Authorization Bearer + X-Agora-Workspace; no X-Agora-Token.
 *  3. No credentials → no auth headers.
 *  4. Session without workspace → Authorization only; no X-Agora-Workspace.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

// localStorage mock — must be set up before any module import that touches it.
const localStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach((k) => delete store[k]) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

import {
  authHeaders,
  hasCredentials,
  getAgoraToken,
  setAgoraToken,
} from '../index'
import {
  setSessionToken,
  setActiveWorkspaceId,
  getSessionToken,
  getActiveWorkspaceId,
} from '../../auth/sessionState'

beforeEach(() => {
  // Reset all state between tests
  localStorageMock.clear()
  setSessionToken(null)
  setActiveWorkspaceId(null)
  // Clear memory token by re-importing is not possible; use setAgoraToken instead
  setAgoraToken(null)
})

describe('authHeaders()', () => {
  it('returns X-Agora-Token when only a legacy token is present', () => {
    setAgoraToken('legacy-master-token')
    const headers = authHeaders()
    expect(headers['X-Agora-Token']).toBe('legacy-master-token')
    expect(headers['Authorization']).toBeUndefined()
    expect(headers['X-Agora-Workspace']).toBeUndefined()
  })

  it('returns Authorization Bearer + X-Agora-Workspace when session + workspace are set', () => {
    setSessionToken('eyJ.supabase.access_token')
    setActiveWorkspaceId('123e4567-e89b-12d3-a456-426614174000')
    const headers = authHeaders()
    expect(headers['Authorization']).toBe('Bearer eyJ.supabase.access_token')
    expect(headers['X-Agora-Workspace']).toBe('123e4567-e89b-12d3-a456-426614174000')
    expect(headers['X-Agora-Token']).toBeUndefined()
  })

  it('does not include X-Agora-Workspace when session has no workspace', () => {
    setSessionToken('eyJ.supabase.access_token')
    // No workspace set
    const headers = authHeaders()
    expect(headers['Authorization']).toBe('Bearer eyJ.supabase.access_token')
    expect(headers['X-Agora-Workspace']).toBeUndefined()
    expect(headers['X-Agora-Token']).toBeUndefined()
  })

  it('returns an empty object when no credentials are present', () => {
    const headers = authHeaders()
    expect(Object.keys(headers)).toHaveLength(0)
  })
})

describe('hasCredentials()', () => {
  it('returns true when a legacy token is set', () => {
    setAgoraToken('some-token')
    expect(hasCredentials()).toBe(true)
  })

  it('returns true when a session token is set', () => {
    setSessionToken('access-token')
    expect(hasCredentials()).toBe(true)
  })

  it('returns false when no token or session is present', () => {
    expect(hasCredentials()).toBe(false)
  })
})
