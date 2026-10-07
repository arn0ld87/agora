import { describe, expect, it } from 'vitest'
import {
  durationToSeconds,
  microsToUsd,
  parseWholeNumber,
  secondsToDuration,
  usdToMicros,
} from '../budgetUnits'

describe('budgetUnits', () => {
  it('rechnet Mikro-USD in USD um und zurück', () => {
    expect(microsToUsd(0)).toBe('0')
    expect(microsToUsd(1_000_000)).toBe('1')
    expect(microsToUsd(12_500_000)).toBe('12.5')
    expect(microsToUsd(1)).toBe('0.000001')
    expect(usdToMicros('12,50')).toBe(12_500_000)
    expect(usdToMicros('12.5')).toBe(12_500_000)
    expect(usdToMicros('0')).toBe(0)
    expect(usdToMicros('0.000001')).toBe(1)
  })

  it('lehnt ungültige USD-Eingaben ab', () => {
    for (const bad of ['', 'abc', '-1', '1e3', '1,2,3', ' ']) expect(usdToMicros(bad)).toBeNull()
  })

  it('zeigt volle Stunden als Stunden, sonst Minuten', () => {
    expect(secondsToDuration(0)).toEqual({ value: '0', unit: 'minutes' })
    expect(secondsToDuration(7200)).toEqual({ value: '2', unit: 'hours' })
    expect(secondsToDuration(5400)).toEqual({ value: '90', unit: 'minutes' })
    expect(secondsToDuration(90)).toEqual({ value: '1.5', unit: 'minutes' })
  })

  it('rechnet Zeiteingaben in Sekunden um', () => {
    expect(durationToSeconds('90', 'minutes')).toBe(5400)
    expect(durationToSeconds('1,5', 'hours')).toBe(5400)
    expect(durationToSeconds('x', 'hours')).toBeNull()
  })

  it('parst ganze Zahlen streng', () => {
    expect(parseWholeNumber('20000000')).toBe(20_000_000)
    expect(parseWholeNumber(' 0 ')).toBe(0)
    for (const bad of ['', '1.5', '-3', '1e6', 'abc']) expect(parseWholeNumber(bad)).toBeNull()
  })
})
