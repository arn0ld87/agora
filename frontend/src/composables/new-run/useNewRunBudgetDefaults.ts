/**
 * Vorbelegung des Budgets im Startdialog aus den Einstellungen.
 *
 * Der Settings-Endpunkt ist für Nicht-Betreiber gesperrt (403). Dann bleibt
 * das Formular leer, und der Dialog sagt, dass die Standardgrenzen der Instanz
 * gelten. `0` heißt „kein Limit“ und wird weggelassen, denn
 * `RunBudgetConfigSchema` verlangt Werte >= 1.
 */
import { ref } from 'vue'
import { useSettingsStore } from '@/store/settings'
import { RunBudgetConfigSchema, type RunBudgetConfig } from '@/contracts/runBudgetContract'
import { BudgetDefaultsSchema } from './newRunSchemas'

export type BudgetDefaultsState = 'loading' | 'ready' | 'unavailable'

/** Reine Umwandlung der Einstellungswerte in ein Run-Budget (oder `null`, wenn nichts begrenzt ist). */
export function budgetFromSettingValues(values: Record<string, unknown>): RunBudgetConfig | null {
  const parsed = BudgetDefaultsSchema.safeParse(values)
  if (!parsed.success) return null
  const d = parsed.data
  const candidate: Record<string, unknown> = {}
  if (d.AGORA_SIM_DEFAULT_MAX_TOKENS) candidate.max_tokens = d.AGORA_SIM_DEFAULT_MAX_TOKENS
  if (d.AGORA_SIM_DEFAULT_MAX_COST_MICROS) candidate.max_cost_micros = d.AGORA_SIM_DEFAULT_MAX_COST_MICROS
  if (d.AGORA_SIM_DEFAULT_MAX_DURATION_SECONDS) {
    candidate.max_duration_seconds = d.AGORA_SIM_DEFAULT_MAX_DURATION_SECONDS
  }
  if (d.AGORA_SIM_DEFAULT_MAX_LLM_CALLS) candidate.max_llm_calls = d.AGORA_SIM_DEFAULT_MAX_LLM_CALLS
  if (Object.keys(candidate).length === 0) return null
  if (d.AGORA_SIM_DEFAULT_BUDGET_ENFORCEMENT) candidate.enforcement = d.AGORA_SIM_DEFAULT_BUDGET_ENFORCEMENT
  const budget = RunBudgetConfigSchema.safeParse(candidate)
  return budget.success ? budget.data : null
}

export function useNewRunBudgetDefaults() {
  const state = ref<BudgetDefaultsState>('loading')
  const defaults = ref<RunBudgetConfig | null>(null)

  async function load(): Promise<void> {
    state.value = 'loading'
    try {
      const store = useSettingsStore()
      await store.ensureLoaded()
      const values: Record<string, unknown> = {}
      for (const item of store.fields['budget'] ?? []) values[item.key] = item.value
      defaults.value = budgetFromSettingValues(values)
      state.value = 'ready'
    } catch {
      defaults.value = null
      state.value = 'unavailable'
    }
  }

  return { state, defaults, load }
}
