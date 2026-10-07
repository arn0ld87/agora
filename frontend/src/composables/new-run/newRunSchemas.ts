/**
 * Zod-Schemas für die Antworten, die der Startdialog „Neuer Lauf“ auswertet.
 * Der Dialog braucht von `/simulation/create` nur die ID des angelegten Laufs.
 */
import { z } from 'zod'

export const CreatedSimulationSchema = z
  .object({ simulation_id: z.string().min(1) })
  .passthrough()
export type CreatedSimulation = z.infer<typeof CreatedSimulationSchema>

const grenze = z.coerce.number().int().min(0).optional()

/** Vorbelegung des Budgets aus den Einstellungen (Abschnitt `budget`). */
export const BudgetDefaultsSchema = z.object({
  AGORA_SIM_DEFAULT_MAX_TOKENS: grenze,
  AGORA_SIM_DEFAULT_MAX_COST_MICROS: grenze,
  AGORA_SIM_DEFAULT_MAX_DURATION_SECONDS: grenze,
  AGORA_SIM_DEFAULT_MAX_LLM_CALLS: grenze,
  AGORA_SIM_DEFAULT_BUDGET_ENFORCEMENT: z.enum(['soft', 'hard']).optional(),
})
export type BudgetDefaults = z.infer<typeof BudgetDefaultsSchema>
