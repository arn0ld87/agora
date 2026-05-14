/**
 * apiKeys-Store — Vitest-Smokes (Slice G2).
 *
 * Tests:
 *  1. list() setzt items korrekt.
 *  2. create() setzt lastCreatedToken + pusht key an ersten Position.
 *  3. revoke() ersetzt das betroffene Item mit der revoked-Version.
 *  4. clearLastCreatedToken() löscht den Klartext-Token.
 *  5. list() setzt error bei API-Fehler.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// localStorage-Mock (vor allen Modulimporten)
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

// Mock API-Modul — verhindert echte HTTP-Calls
vi.mock('../../api/apiKeys', () => ({
  listApiKeys: vi.fn(),
  createApiKey: vi.fn(),
  revokeApiKey: vi.fn(),
}))

import { listApiKeys, createApiKey, revokeApiKey } from '../../api/apiKeys'
import { useApiKeysStore } from '../apiKeys'
import type { ApiKeyModel } from '../../contracts/apiKeysContract'

type MockFn = ReturnType<typeof vi.fn>
const _listApiKeys = listApiKeys as unknown as MockFn
const _createApiKey = createApiKey as unknown as MockFn
const _revokeApiKey = revokeApiKey as unknown as MockFn

// --- Fixtures ---
function makeKey(overrides: Partial<ApiKeyModel> = {}): ApiKeyModel {
  return {
    id: 'key-001',
    label: 'Test-Key',
    prefix: 'ago_abcd1234',
    scopes: ['read'],
    status: 'active',
    hashed_token: 'h-mock-001',
    created_at: '2026-05-14T10:00:00Z',
    last_used_at: null,
    revoked_at: null,
    ...overrides,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('useApiKeysStore', () => {
  it('Test 1: list() setzt items aus API-Response', async () => {
    const key1 = makeKey({ id: 'key-001', label: 'Key 1' })
    const key2 = makeKey({ id: 'key-002', label: 'Key 2', scopes: ['read', 'write'] })
    _listApiKeys.mockResolvedValue({ items: [key1, key2], total: 2 })

    const store = useApiKeysStore()
    await store.list()

    expect(store.items).toHaveLength(2)
    expect(store.items[0].id).toBe('key-001')
    expect(store.items[1].id).toBe('key-002')
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it('Test 2: create() setzt lastCreatedToken + pusht key an erster Position', async () => {
    const existingKey = makeKey({ id: 'old-key', label: 'Existing' })
    _listApiKeys.mockResolvedValue({ items: [existingKey], total: 1 })

    const newKey = makeKey({ id: 'new-key', label: 'Neuer Key', scopes: ['read', 'write'] })
    const token = 'ago_' + 'a'.repeat(48)
    _createApiKey.mockResolvedValue({ key: newKey, token })

    const store = useApiKeysStore()
    await store.list()
    await store.create('Neuer Key', ['read', 'write'])

    expect(store.lastCreatedToken).toBe(token)
    expect(store.items[0].id).toBe('new-key')
    expect(store.items[1].id).toBe('old-key')
    expect(store.creating).toBe(false)
    expect(store.error).toBeNull()
  })

  it('Test 3: revoke() ersetzt Item mit revoked-Version', async () => {
    const key = makeKey({ id: 'key-001', status: 'active' })
    _listApiKeys.mockResolvedValue({ items: [key], total: 1 })

    const revokedKey: ApiKeyModel = { ...key, status: 'revoked', revoked_at: '2026-05-14T12:00:00Z' }
    _revokeApiKey.mockResolvedValue(revokedKey)

    const store = useApiKeysStore()
    await store.list()
    await store.revoke('key-001')

    expect(store.items).toHaveLength(1)
    expect(store.items[0].status).toBe('revoked')
    expect(store.items[0].revoked_at).toBe('2026-05-14T12:00:00Z')
    expect(store.error).toBeNull()
  })

  it('Test 4: clearLastCreatedToken() setzt lastCreatedToken auf null', async () => {
    const newKey = makeKey({ id: 'new-key', label: 'Test' })
    const token = 'ago_' + 'b'.repeat(48)
    _createApiKey.mockResolvedValue({ key: newKey, token })

    const store = useApiKeysStore()
    await store.create('Test', ['read'])

    expect(store.lastCreatedToken).toBe(token)
    store.clearLastCreatedToken()
    expect(store.lastCreatedToken).toBeNull()
  })

  it('Test 5: list() setzt error bei API-Fehler', async () => {
    _listApiKeys.mockRejectedValue(new Error('Netzwerkfehler'))

    const store = useApiKeysStore()
    await expect(store.list()).rejects.toThrow('Netzwerkfehler')

    expect(store.error).toBe('Netzwerkfehler')
    expect(store.loading).toBe(false)
    expect(store.items).toHaveLength(0)
  })
})
