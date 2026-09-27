import { beforeEach, describe, expect, it, vi } from 'vitest'

const operator = vi.hoisted(() => ({ value: false }))
const effective = vi.hoisted(() => ({
  ensureLoaded: vi.fn().mockResolvedValue(undefined),
  effectiveRef: { value: { provider_connection_id: 'operator', model_id: 'gpt-4o', source: 'workspace-default' } },
}))
const override = vi.hoisted(() => ({ value: null as null | { provider_connection_id: string; model_id: string; source: 'explicit' } }))

vi.mock('../useOperatorAccess', () => ({ useOperatorAccess: () => operator }))
vi.mock('../useEffectiveModelSelection', () => ({ useEffectiveModelSelection: () => effective }))
vi.mock('@/store/runModelOverride', () => ({ getRunModelOverride: () => override.value }))

import { useRunModelResolver } from '../useRunModelResolver'

describe('useRunModelResolver — JWT workspace', () => {
  beforeEach(() => {
    operator.value = false
    override.value = null
    effective.ensureLoaded.mockClear()
  })

  it('verwendet ohne expliziten Pick keine globale Betreiber-Route', async () => {
    const result = await useRunModelResolver().resolveRunModel()
    expect(result).toEqual({ ref: null, usedRunOverride: false })
    expect(effective.ensureLoaded).not.toHaveBeenCalled()
  })

  it('leitet den expliziten Workspace-Pick weiter', async () => {
    override.value = { provider_connection_id: 'minimax', model_id: 'MiniMax-M2.5', source: 'explicit' }
    const result = await useRunModelResolver().resolveRunModel()
    expect(result).toEqual({
      ref: { provider_connection_id: 'minimax', model_id: 'MiniMax-M2.5', source: 'explicit' },
      usedRunOverride: true,
    })
    expect(effective.ensureLoaded).not.toHaveBeenCalled()
  })
})
