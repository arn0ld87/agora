import { describe, expect, it } from 'vitest'
import { isHandMade, originOf } from '../graphOrigin'

describe('originOf', () => {
  it('liest manual und edited und behandelt alles andere als extrahiert', () => {
    expect(originOf({ provenance: { origin: 'manual' } })).toBe('manual')
    expect(originOf({ provenance: { origin: 'edited' } })).toBe('edited')
    expect(originOf({ provenance: { origin: null } })).toBeNull()
    expect(originOf({ provenance: {} })).toBeNull()
    expect(originOf({})).toBeNull()
    expect(originOf(null)).toBeNull()
    expect(originOf('nope')).toBeNull()
  })

  it('isHandMade ist genau für manual oder edited wahr', () => {
    expect(isHandMade({ provenance: { origin: 'manual' } })).toBe(true)
    expect(isHandMade({ provenance: { origin: 'edited' } })).toBe(true)
    expect(isHandMade({ provenance: { origin: null }, episode_ids: ['ep1'] })).toBe(false)
  })
})