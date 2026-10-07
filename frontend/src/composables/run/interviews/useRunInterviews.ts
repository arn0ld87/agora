/**
 * Interviews eines Laufs (#1805, Etappe 6): Verlauf, Einzel- und Gruppenfrage.
 *
 * Schnittstelle (die View legt das Composable einmal an und verteilt es per
 * `provide`, siehe `useRunInterviewsContext`):
 * - `conversations`  Gespräche je Persona aus dem Verlauf plus Sitzungszüge.
 * - `groupResults`   Gruppenfragen DIESER Sitzung (der Server kennt keine Gruppen).
 * - `loading`, `error`  Laden des Verlaufs; `error` ist ein sichtbarer Text.
 * - `reload()`       Verlauf neu laden.
 * - `ask(agentId, text)`  Einzelfrage; `askGroup(agentIds, text)`  Gruppenfrage
 *   mit Ergebnis `{asked, answered, failed}`.
 * - `sending`, `sendError`  Zustand der letzten Frage; `budgetExceeded` ist
 *   wahr, wenn das Backend wegen eines erschöpften Budgets abbrach (nie als
 *   leere Antwort behandelt).
 * - `available`, `unavailableReason`  falsch bei 503 (keine Umgebung, keine
 *   persistierten Personas).
 * - `modelLabel`     Modell des Laufs (`llm_model` der Konfiguration), sonst null.
 *   Der Endpunkt nimmt kein Modell je Frage an.
 * - `largeGroupWarning(n)`  wahr, wenn eine Gruppenfrage an `n` Personas die
 *   Frist des Backends wahrscheinlich reißt.
 */
import { computed, inject, ref, toValue, watch, type ComputedRef, type InjectionKey, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { z } from 'zod'
import { askPersonas, getInterviewHistory, type InterviewAnswer } from '@/api/interviews'
import { getSimulationConfig } from '@/api/simulation'
import { isApiError } from '@/api/envelope'
import type { InterviewHistoryItem } from '@/contracts/interviewContract'
import { interviewErrorMessage } from '@/utils/interviewErrorMessage'
import { readEnvelope } from '../simulation/simulationEnvelope'
import {
  buildConversations,
  buildGroupConversation,
  type GroupAnswer,
  type GroupConversation,
  type GroupRecord,
  type InterviewTurn,
  stripInterviewPrefix,
  type PersonaConversation,
  type SessionTurn,
} from './conversations'

/**
 * Ab dieser Zahl befragter Personas warnt die Oberfläche. Herleitung: Das
 * Backend setzt für `interview/batch` eine Frist von 120 s und arbeitet mit
 * 4 parallelen Arbeitern. Nimmt man grob 30 s je Antwort an (ANNAHME, nicht
 * gemessen), schaffen 4 Arbeiter in 120 s etwa 4 × 120 / 30 = 16 Antworten.
 */
export const GROUP_WARN_THRESHOLD = 16

/** Wie viele Verlaufszeilen geladen werden (Backend-Standard wäre 100). */
export const HISTORY_LIMIT = 500

/** `busy`: eine Frage läuft schon, nichts gesendet. `stale`: die Simulation wechselte, Ergebnis verworfen. */
export type AskStatus = 'answered' | 'failed' | 'budget' | 'unavailable' | 'busy' | 'stale'

export interface AskOutcome {
  status: AskStatus
  answer: string | null
  error: string | null
}

export interface GroupOutcome {
  asked: number
  answered: number
  failed: number
}

const ConfigDataSchema = z.object({ llm_model: z.string().nullish() }).passthrough()

/**
 * Felder des 409-Envelopes `budget_exceeded` (flach im Body, siehe
 * `_budget_exceeded_as_conflict` im Backend). Alles optional: fehlt etwas,
 * zeigt die Oberfläche nur die Meldung, nie geratene Zahlen.
 */
const BudgetBodySchema = z
  .object({
    error: z.string().nullish(),
    termination_reason: z.string().nullish(),
    dimension: z.string().nullish(),
    observed: z.number().nullish(),
    threshold: z.number().nullish(),
  })
  .passthrough()

export interface BudgetDetail {
  message: string
  reason: string | null
  dimension: string | null
  observed: number | null
  threshold: number | null
}

function budgetDetailOf(err: unknown, message: string): BudgetDetail {
  const parsed = isApiError(err) ? BudgetBodySchema.safeParse(err.originalResponse) : null
  const body = parsed?.success ? parsed.data : null
  return {
    message,
    reason: body?.termination_reason ?? null,
    dimension: body?.dimension ?? null,
    observed: body?.observed ?? null,
    threshold: body?.threshold ?? null,
  }
}

/**
 * Ein Budgetabbruch ist ausschließlich der 409-Envelope `budget_exceeded`.
 * Keine Freitext-Heuristik: Fehlertexte einzelner Batch-Einträge (etwa
 * "Batch-Deadline … überschritten") sind gewöhnliche Fehler des Eintrags.
 */
export function isBudgetFailure(err: unknown): boolean {
  return isApiError(err) && err.status === 409 && err.code === 'budget_exceeded'
}

function nowIso(): string {
  return new Date().toISOString()
}

export interface UseRunInterviews {
  conversations: ComputedRef<PersonaConversation[]>
  groupResults: ComputedRef<GroupConversation[]>
  loading: Readonly<Ref<boolean>>
  error: Readonly<Ref<string | null>>
  sending: Readonly<Ref<boolean>>
  sendError: Readonly<Ref<string | null>>
  budgetExceeded: Readonly<Ref<boolean>>
  budgetDetail: Readonly<Ref<BudgetDetail | null>>
  available: Readonly<Ref<boolean>>
  unavailableReason: Readonly<Ref<string | null>>
  modelLabel: Readonly<Ref<string | null>>
  reload: () => Promise<void>
  ask: (agentId: number, text: string) => Promise<AskOutcome>
  askGroup: (agentIds: readonly number[], text: string) => Promise<GroupOutcome>
  largeGroupWarning: (count: number) => boolean
}

export interface UseRunInterviewsOptions {
  /** Übersetzer; ohne Angabe `useI18n().t` (Aufruf dann nur in `setup`). */
  t?: (key: string) => string
}

export function useRunInterviews(
  simulationId: Ref<string> | string,
  options: UseRunInterviewsOptions = {},
): UseRunInterviews {
  const t = options.t ?? (useI18n().t as (key: string) => string)

  const history = ref<InterviewHistoryItem[]>([])
  const sessionTurns = ref<SessionTurn[]>([])
  const groups = ref<GroupRecord[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const sending = ref(false)
  const sendError = ref<string | null>(null)
  const budgetExceeded = ref(false)
  const budgetDetail = ref<BudgetDetail | null>(null)
  const available = ref(true)
  const unavailableReason = ref<string | null>(null)
  const modelLabel = ref<string | null>(null)
  let token = 0
  let groupSeq = 0

  function markUnavailable(err: unknown): boolean {
    if (isApiError(err) && err.status === 503) {
      available.value = false
      unavailableReason.value = err.message
      return true
    }
    return false
  }

  async function reload(): Promise<void> {
    const id = toValue(simulationId)
    if (!id) return
    const mine = ++token
    loading.value = true
    error.value = null
    try {
      const rows = await getInterviewHistory(id, { limit: HISTORY_LIMIT })
      if (mine !== token) return
      history.value = rows
      // Der Verlauf ist maßgeblich: ein Sitzungszug fällt weg, sobald er dort steht.
      // Fehlgeschlagene Züge tauchen im Verlauf nie auf und bleiben sichtbar; eine
      // Antwort, die der Verlauf (noch) nicht enthält, geht ebenfalls nicht verloren.
      sessionTurns.value = sessionTurns.value.filter(
        (s) =>
          s.turn.error ||
          !rows.some(
            (r) =>
              r.agent_id === s.agentId &&
              stripInterviewPrefix(r.prompt) === s.turn.question &&
              (r.response ?? null) === s.turn.answer,
          ),
      )
    } catch (err) {
      if (mine !== token) return
      if (!markUnavailable(err)) error.value = interviewErrorMessage(err, t)
    } finally {
      if (mine === token) loading.value = false
    }
  }

  async function loadModel(): Promise<void> {
    const id = toValue(simulationId)
    if (!id) return
    try {
      const raw = await getSimulationConfig(id)
      const model = readEnvelope(raw, ConfigDataSchema, 'simulation/config').llm_model ?? null
      if (toValue(simulationId) === id) modelLabel.value = model
    } catch (err) {
      if (toValue(simulationId) !== id) return
      // Das Modell ist eine Zusatzangabe; fehlt sie, zeigt die Oberfläche "unbekannt".
      console.warn('[run-interviews] Modell des Laufs nicht ladbar', {
        simulationId: id,
        error: err instanceof Error ? err.message : String(err),
      })
      modelLabel.value = null
    }
  }

  /**
   * Eintrag zu `agentId`; bei mehreren Plattformen (lebende Umgebung befragt
   * beide) zählt die mit Antwort für die Zusammenfassung der Frage. Die
   * Einzelgespräche zeigen nach dem Nachladen beide Zeilen aus dem Verlauf,
   * je mit Plattform.
   */
  function pick(answers: readonly InterviewAnswer[], agentId: number): InterviewAnswer | null {
    const mine = answers.filter((a) => a.agentId === agentId)
    return mine.find((a) => a.response && !a.error) ?? mine[0] ?? null
  }

  async function send(
    agentIds: readonly number[],
    text: string,
  ): Promise<{ answers: GroupAnswer[]; status: AskStatus; message: string | null }> {
    const id = toValue(simulationId)
    const stale = (): boolean => toValue(simulationId) !== id
    const staleResult = { answers: [] as GroupAnswer[], status: 'stale' as AskStatus, message: null }
    sending.value = true
    sendError.value = null
    budgetExceeded.value = false
    budgetDetail.value = null
    const asked = nowIso()
    try {
      const results = await askPersonas(
        id,
        agentIds.map((agentId) => ({ agentId, prompt: text })),
      )
      if (stale()) return staleResult
      const answers: GroupAnswer[] = agentIds.map((agentId) => {
        const e = pick(results, agentId)
        const failure = e?.error || (e && !e.response ? t('views.run.interviews.noAnswer') : null)
        return {
          agentId,
          answer: failure ? null : (e?.response ?? null),
          error: e ? failure : t('views.run.interviews.noAnswer'),
          timestamp: e?.timestamp ?? asked,
          platform: e?.platform ?? null,
        }
      })
      // Fehler je Eintrag bleiben am Eintrag; ein Budgetabbruch kommt nur als 409.
      return { answers, status: 'answered', message: null }
    } catch (err) {
      if (stale()) return staleResult
      const unavailable = markUnavailable(err)
      const message = err instanceof Error ? err.message : String(err)
      const budget = isBudgetFailure(err)
      budgetExceeded.value = budget
      budgetDetail.value = budget ? budgetDetailOf(err, message) : null
      sendError.value = budget
        ? `${t('views.run.interviews.budgetExceeded')} ${message}`
        : interviewErrorMessage(err, t)
      return {
        answers: agentIds.map((agentId) => ({
          agentId,
          answer: null,
          error: sendError.value,
          timestamp: asked,
          platform: null,
        })),
        status: unavailable ? 'unavailable' : budget ? 'budget' : 'failed',
        message: sendError.value,
      }
    } finally {
      // Nach einem Wechsel der Simulation hat der Watcher `sending` schon zurückgesetzt;
      // eine neue Frage dort darf der späte Abschluss der alten nicht entsperren.
      if (!stale()) sending.value = false
    }
  }

  function turnOf(question: string, a: GroupAnswer): InterviewTurn {
    return { question, answer: a.answer, timestamp: a.timestamp, platform: a.platform, error: a.error }
  }

  async function ask(agentId: number, text: string): Promise<AskOutcome> {
    const question = text.trim()
    if (!question) return { status: 'failed', answer: null, error: null }
    if (sending.value) return { status: 'busy', answer: null, error: null }
    const res = await send([agentId], question)
    if (res.status === 'stale') return { status: 'stale', answer: null, error: null }
    const a = res.answers[0]
    // Optimistisch anhängen; der Nachladen unten ersetzt beantwortete Züge durch den Verlauf.
    sessionTurns.value = [...sessionTurns.value, { agentId, turn: turnOf(question, a) }]
    // Ein Fehler dieser einen Antwort bleibt neben dem Eingabefeld stehen, nicht nur im Verlauf.
    if (a.error && !sendError.value) sendError.value = a.error
    if (!a.error) await reload()
    const status: AskStatus = a.error ? (res.status === 'answered' ? 'failed' : res.status) : 'answered'
    return { status, answer: a.answer, error: a.error }
  }

  async function askGroup(agentIds: readonly number[], text: string): Promise<GroupOutcome> {
    const question = text.trim()
    const ids = [...new Set(agentIds)]
    if (!question || ids.length === 0) return { asked: 0, answered: 0, failed: 0 }
    if (sending.value) return { asked: 0, answered: 0, failed: 0 }
    const res = await send(ids, question)
    if (res.status === 'stale') return { asked: 0, answered: 0, failed: 0 }
    groupSeq += 1
    groups.value = [
      ...groups.value,
      { groupId: `${Date.now().toString(36)}${groupSeq}`, question, askedAt: nowIso(), answers: res.answers },
    ]
    sessionTurns.value = [
      ...sessionTurns.value,
      ...res.answers.map((a) => ({ agentId: a.agentId, turn: turnOf(question, a) })),
    ]
    const answered = res.answers.filter((a) => !a.error).length
    if (answered > 0) await reload()
    return { asked: ids.length, answered, failed: ids.length - answered }
  }

  watch(
    () => toValue(simulationId),
    () => {
      history.value = []
      sessionTurns.value = []
      groups.value = []
      sending.value = false
      modelLabel.value = null
      sendError.value = null
      budgetExceeded.value = false
      budgetDetail.value = null
      available.value = true
      unavailableReason.value = null
      void reload()
      void loadModel()
    },
  )
  void reload()
  void loadModel()

  return {
    conversations: computed(() => buildConversations(history.value, sessionTurns.value)),
    groupResults: computed(() => [...groups.value].reverse().map(buildGroupConversation)),
    loading: computed(() => loading.value),
    error: computed(() => error.value),
    sending: computed(() => sending.value),
    sendError: computed(() => sendError.value),
    budgetExceeded: computed(() => budgetExceeded.value),
    budgetDetail: computed(() => budgetDetail.value),
    available: computed(() => available.value),
    unavailableReason: computed(() => unavailableReason.value),
    modelLabel: computed(() => modelLabel.value),
    reload,
    ask,
    askGroup,
    largeGroupWarning: (count: number) => count > GROUP_WARN_THRESHOLD,
  }
}

export const RUN_INTERVIEWS_KEY: InjectionKey<UseRunInterviews> = Symbol('run-interviews')

/**
 * Das von `RunInterviewsView` bereitgestellte Composable. Ohne Elternansicht
 * (Einzeltests der Komponenten) liefert es einen leeren, inerten Zustand
 * statt zu werfen.
 */
export function useRunInterviewsContext(): UseRunInterviews {
  const injected = inject(RUN_INTERVIEWS_KEY, null)
  if (injected) return injected
  const idle = computed(() => false)
  return {
    conversations: computed(() => []),
    groupResults: computed(() => []),
    loading: idle,
    error: computed(() => null),
    sending: idle,
    sendError: computed(() => null),
    budgetExceeded: idle,
    budgetDetail: computed(() => null),
    available: computed(() => true),
    unavailableReason: computed(() => null),
    modelLabel: computed(() => null),
    reload: async () => {},
    ask: async () => ({ status: 'failed', answer: null, error: null }),
    askGroup: async () => ({ asked: 0, answered: 0, failed: 0 }),
    largeGroupWarning: (count: number) => count > GROUP_WARN_THRESHOLD,
  }
}
