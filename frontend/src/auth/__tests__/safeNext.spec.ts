import { describe, it, expect } from 'vitest'
import { safeNext } from '../safeNext'

describe('safeNext', () => {
  it.each([
    ['/ablage', '/ablage'],
    ['/runs/1?tab=a', '/runs/1?tab=a'],
    ['//evil.example', '/'],
    ['/\\evil.example', '/'],
    ['https://evil.example', '/'],
    ['javascript:alert(1)', '/'],
    ['', '/'],
    [undefined, '/'],
    [['/a'], '/'],
  ])('%j → %s', (input, expected) => {
    expect(safeNext(input)).toBe(expected)
  })
})
