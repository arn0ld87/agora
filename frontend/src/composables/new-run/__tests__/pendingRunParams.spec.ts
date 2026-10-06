import { beforeEach, describe, expect, it } from 'vitest'
import {
  PENDING_RUN_PARAMS_PREFIX,
  clearPendingRunParams,
  pendingRunParamsQuery,
  readPendingRunParams,
  writePendingRunParams,
} from '../pendingRunParams'
import { budgetFromSettingValues } from '../useNewRunBudgetDefaults'

const BUDGET = { schema_version: 1 as const, max_tokens: 1000, enforcement: 'hard' as const, currency: 'USD' }

describe('pendingRunParams', () => {
  beforeEach(() => window.sessionStorage.clear())

  it('schreibt, liest und löscht je simulationId', () => {
    writePendingRunParams('s1', { maxRounds: 12, simulationDays: 2, budget: BUDGET })
    writePendingRunParams('s2', { maxRounds: 5, simulationDays: null, budget: null })
    expect(readPendingRunParams('s1')).toEqual({ maxRounds: 12, simulationDays: 2, budget: BUDGET })
    expect(readPendingRunParams('s2')?.maxRounds).toBe(5)
    clearPendingRunParams('s1')
    expect(readPendingRunParams('s1')).toBeNull()
    expect(readPendingRunParams('s2')).not.toBeNull()
  })

  it('pendingRunParamsQuery liefert die fertige Route-Query', () => {
    writePendingRunParams('s1', { maxRounds: 12, simulationDays: 2, budget: BUDGET })
    expect(pendingRunParamsQuery('s1')).toEqual({
      maxRounds: '12',
      simulationDays: '2',
      budget: JSON.stringify(BUDGET),
    })
    expect(pendingRunParamsQuery('unbekannt')).toEqual({})
  })

  it('lässt Nullwerte aus der Query weg', () => {
    writePendingRunParams('s1', { maxRounds: 24, simulationDays: null, budget: null })
    expect(pendingRunParamsQuery('s1')).toEqual({ maxRounds: '24' })
  })

  it('beschädigte oder ungültige Einträge gelten als nicht vorhanden', () => {
    window.sessionStorage.setItem(`${PENDING_RUN_PARAMS_PREFIX}s1`, '{kaputt')
    window.sessionStorage.setItem(
      `${PENDING_RUN_PARAMS_PREFIX}s2`,
      JSON.stringify({ maxRounds: 0, simulationDays: 999, budget: null }),
    )
    expect(readPendingRunParams('s1')).toBeNull()
    expect(readPendingRunParams('s2')).toBeNull()
    expect(pendingRunParamsQuery('s2')).toEqual({})
  })

  it('schreibt keine ungültigen Werte', () => {
    writePendingRunParams('s1', { maxRounds: 0, simulationDays: 1, budget: null })
    expect(window.sessionStorage.getItem(`${PENDING_RUN_PARAMS_PREFIX}s1`)).toBeNull()
  })
})

describe('budgetFromSettingValues', () => {
  it('lässt 0 (kein Limit) weg und übernimmt die Durchsetzung', () => {
    expect(
      budgetFromSettingValues({
        AGORA_SIM_DEFAULT_MAX_TOKENS: 20000000,
        AGORA_SIM_DEFAULT_MAX_COST_MICROS: 0,
        AGORA_SIM_DEFAULT_MAX_DURATION_SECONDS: 3600,
        AGORA_SIM_DEFAULT_MAX_LLM_CALLS: 0,
        AGORA_SIM_DEFAULT_BUDGET_ENFORCEMENT: 'soft',
      }),
    ).toEqual({
      schema_version: 1,
      max_tokens: 20000000,
      max_duration_seconds: 3600,
      enforcement: 'soft',
      currency: 'USD',
    })
  })

  it('liefert null, wenn nichts begrenzt ist oder die Werte unlesbar sind', () => {
    expect(budgetFromSettingValues({ AGORA_SIM_DEFAULT_MAX_TOKENS: 0 })).toBeNull()
    expect(budgetFromSettingValues({ AGORA_SIM_DEFAULT_MAX_TOKENS: 'viel' })).toBeNull()
    expect(budgetFromSettingValues({})).toBeNull()
  })
})
