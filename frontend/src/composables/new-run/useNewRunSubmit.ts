/**
 * Aufrufe des Startdialogs auf einem vorhandenen Graphen.
 *
 * - `createOnly`: `POST /simulation/create`, dann zur Übersicht des Laufs.
 * - `createAndPrepare`: create, dann `POST /simulation/prepare`, Startwerte
 *   (Tage, Runden, Budget) in `pendingRunParams`, dann zur Übersicht. Die
 *   Simulation selbst startet die Übersicht.
 *
 * Schlägt `prepare` nach erfolgreichem `create` fehl, bleibt der angelegte Lauf
 * sichtbar (`createdSimulationId`): der Dialog nennt ihn, ein erneuter Versuch
 * legt keinen zweiten an.
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { createSimulation, createSimulationFromPersonas, prepareSimulation } from '@/api/simulation'
import type { PrepareSimulationData } from '@/api/simulation'
import type { ApiEnvelope } from '@/api/envelope'
import type { AiModelRef } from '@/contracts/aiModelRef'
import type { RunBudgetConfig } from '@/contracts/runBudgetContract'
import type { ActivityMode } from '@/contracts/simulationActivityContract'
import { errorText } from '@/composables/graph-library/useProjectGraph'
import { CreatedSimulationSchema } from './newRunSchemas'
import { writePendingRunParams } from './pendingRunParams'

export interface ExistingGraphRunInput {
  projectId: string
  graphId: string
  language: string
  /** `null`: keine Obergrenze gesetzt. */
  maxAgents: number | null
  contestedQuestion: string
  activityMode: ActivityMode
  profileId: string | null
  /** Ausdrücklich gewähltes Modell; `null`: der Kanon des Servers gilt. */
  modelRef: AiModelRef | null
  /** Nur gesetzt, wenn der Nutzer das vorbelegte Budget geändert hat. */
  budget: RunBudgetConfig | null
  maxRounds: number
  simulationDays: number
}

/** Lauf aus einem Personasatz, ohne Graph (#1807, Maintainer-Entscheid). */
export interface PersonaSetRunInput {
  personaSetId: string
  /** Pflicht auch ohne Graph: der Lauf braucht eine Fragestellung. */
  simulationRequirement: string
  language: string
  maxRounds: number
  simulationDays: number
  budget: RunBudgetConfig | null
}

export type NewRunPhase = 'create' | 'prepare'

function failure(res: ApiEnvelope<unknown>, fallback: string): string {
  return !res.success && typeof res.error === 'string' && res.error ? res.error : fallback
}

export function useNewRunSubmit() {
  const { t } = useI18n()
  const router = useRouter()
  const busy = ref(false)
  const phase = ref<NewRunPhase | null>(null)
  const error = ref('')
  const createdSimulationId = ref<string | null>(null)

  function goToOverview(simulationId: string): Promise<unknown> {
    return router.push({ name: 'RunOverview', params: { simulationId } })
  }

  /** Legt den Lauf an oder gibt den bereits angelegten zurück; `null` bei Fehler. */
  async function ensureCreated(input: ExistingGraphRunInput): Promise<string | null> {
    if (createdSimulationId.value) return createdSimulationId.value
    phase.value = 'create'
    try {
      const res = await createSimulation({
        project_id: input.projectId,
        graph_id: input.graphId,
        enable_twitter: true,
        enable_reddit: true,
      })
      if (!res.success) {
        error.value = failure(res, t('views.newRun.errors.create'))
        return null
      }
      const parsed = CreatedSimulationSchema.safeParse(res.data)
      if (!parsed.success) {
        error.value = t('views.newRun.errors.createShape')
        return null
      }
      createdSimulationId.value = parsed.data.simulation_id
      return parsed.data.simulation_id
    } catch (caught) {
      error.value = errorText(caught, t('views.newRun.errors.create'))
      return null
    }
  }

  async function createOnly(input: ExistingGraphRunInput): Promise<void> {
    if (busy.value) return
    busy.value = true
    error.value = ''
    try {
      const id = await ensureCreated(input)
      if (id) await goToOverview(id)
    } finally {
      busy.value = false
      phase.value = null
    }
  }

  function buildPreparePayload(simulationId: string, input: ExistingGraphRunInput): PrepareSimulationData {
    const payload: PrepareSimulationData = {
      simulation_id: simulationId,
      use_llm_for_profiles: true,
      language: input.language,
      activity_mode: input.activityMode,
    }
    if (input.profileId) {
      payload.llm_profile_id = input.profileId
    } else if (input.modelRef) {
      payload.ai_model_ref = {
        provider_connection_id: input.modelRef.provider_connection_id,
        model_id: input.modelRef.model_id,
        source: 'explicit',
      }
    }
    if (input.maxAgents !== null) payload.max_agents = Math.max(10, input.maxAgents)
    const question = input.contestedQuestion.trim()
    if (question) payload.contested_question = question
    if (input.budget) payload.budget = input.budget
    return payload
  }

  async function createAndPrepare(input: ExistingGraphRunInput): Promise<void> {
    if (busy.value) return
    busy.value = true
    error.value = ''
    try {
      const id = await ensureCreated(input)
      if (!id) return
      phase.value = 'prepare'
      let message: string | null = null
      try {
        const res = await prepareSimulation(buildPreparePayload(id, input))
        if (!res.success) message = failure(res, t('views.newRun.errors.prepare'))
      } catch (caught) {
        message = errorText(caught, t('views.newRun.errors.prepare'))
      }
      if (message !== null) {
        // Der Lauf existiert: der Fehler nennt ihn, statt ihn zu verschweigen.
        error.value = t('views.newRun.errors.prepareAfterCreate', { id, message })
        return
      }
      writePendingRunParams(id, {
        maxRounds: input.maxRounds,
        simulationDays: input.simulationDays,
        budget: input.budget,
      })
      await goToOverview(id)
    } finally {
      busy.value = false
      phase.value = null
    }
  }

  /**
   * Lauf aus einem Personasatz, **ohne Graph** (#1807).
   *
   * Bewusst ein eigener Weg und nicht der regulaere mit leerem `graph_id`:
   * `/api/simulation/create` verlangt einen Graphen, und der Weg soll das auch
   * weiterhin. `create-from-personas` legt den Lauf an und bereitet ihn in einem
   * Schritt vor — deshalb wird hier kein `prepare` nachgeschoben (Maintainer-
   * Entscheid: „Prepare bleibt unberührt").
   *
   * Berichte gibt es fuer diese Laeufe nicht; der Satz wird nach erfolgreicher
   * Vorbereitung serverseitig gesperrt.
   */
  async function createFromPersonaSet(input: PersonaSetRunInput): Promise<void> {
    if (busy.value) return
    // Vor dem Server, nicht danach: der Endpunkt lehnt beides mit 400 ab, und
    // ein Fehlversuch mit klarer Ursache waere eine Anfrage, die der Nutzer
    // nicht verstehen kann.
    if (!input.personaSetId.trim()) {
      error.value = t('views.newRun.errors.noPersonaSet')
      return
    }
    if (!input.simulationRequirement.trim()) {
      error.value = t('views.newRun.errors.noRequirement')
      return
    }
    busy.value = true
    error.value = ''
    phase.value = 'create'
    try {
      const res = await createSimulationFromPersonas({
        simulation_requirement: input.simulationRequirement,
        persona_set_id: input.personaSetId,
      })
      if (!res.success) {
        error.value = failure(res, t('views.newRun.errors.createFromPersonaSet'))
        return
      }
      const parsed = CreatedSimulationSchema.safeParse(res.data)
      if (!parsed.success) {
        error.value = t('views.newRun.errors.createShape')
        return
      }
      // Startwerte wie im Graph-Weg: der Lauf ist angelegt und vorbereitet.
      writePendingRunParams(parsed.data.simulation_id, {
        maxRounds: input.maxRounds,
        simulationDays: input.simulationDays,
        budget: input.budget,
      })
      await goToOverview(parsed.data.simulation_id)
    } catch (caught) {
      error.value = errorText(caught, t('views.newRun.errors.createFromPersonaSet'))
    } finally {
      busy.value = false
      phase.value = null
    }
  }

  return { busy, phase, error, createdSimulationId, createOnly, createAndPrepare, createFromPersonaSet }
}
