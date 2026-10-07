/**
 * pendingRunParams — vorgemerkte Startwerte je Lauf (Startdialog „Neuer Lauf“).
 *
 * Der Dialog legt eine Simulation an und bereitet sie vor; gestartet wird sie
 * erst in der Übersicht des Laufs. Damit Tage, Runden und Budget dort ankommen,
 * liegen sie bis dahin in der sessionStorage (tab-lokal, überlebt einen Reload),
 * je `simulationId`. Gelesen wird zod-validiert; ein beschädigter Eintrag gilt
 * als nicht vorhanden. Die Steuerung der Simulation (`useSimulationControl`) liest die
 * Werte beim Start und räumt sie danach ab; auch der Weg über die Personas-Ansicht
 * (`StepEnvSetupView`) legt sie hier ab.
 */
import { z } from 'zod'
import { RunBudgetConfigSchema } from '@/contracts/runBudgetContract'
import { MAX_SIMULATION_DAYS } from '@/contracts/runParamsQuery'

export const PENDING_RUN_PARAMS_PREFIX = 'agora.newRun.pendingParams.'

export const PendingRunParamsSchema = z
  .object({
    maxRounds: z.number().int().min(1).nullable(),
    simulationDays: z.number().int().min(1).max(MAX_SIMULATION_DAYS).nullable(),
    budget: RunBudgetConfigSchema.nullable(),
  })
  .strict()
export type PendingRunParams = z.infer<typeof PendingRunParamsSchema>

function storageOrNull(): Storage | null {
  try {
    if (typeof window === 'undefined') return null
    const ss = window.sessionStorage
    if (!ss || typeof ss.getItem !== 'function') return null
    return ss
  } catch {
    return null
  }
}

const keyOf = (simulationId: string): string => `${PENDING_RUN_PARAMS_PREFIX}${simulationId}`

export function writePendingRunParams(simulationId: string, params: PendingRunParams): void {
  const parsed = PendingRunParamsSchema.safeParse(params)
  const ss = storageOrNull()
  if (!parsed.success || !ss) return
  try {
    ss.setItem(keyOf(simulationId), JSON.stringify(parsed.data))
  } catch {
    /* Speicher voll oder gesperrt: der Start nutzt dann die Auto-Werte. */
  }
}

export function readPendingRunParams(simulationId: string): PendingRunParams | null {
  const ss = storageOrNull()
  if (!ss) return null
  try {
    const raw = ss.getItem(keyOf(simulationId))
    if (!raw) return null
    const parsed = PendingRunParamsSchema.safeParse(JSON.parse(raw))
    return parsed.success ? parsed.data : null
  } catch {
    return null
  }
}

export function clearPendingRunParams(simulationId: string): void {
  try {
    storageOrNull()?.removeItem(keyOf(simulationId))
  } catch {
    /* nichts zu räumen */
  }
}
