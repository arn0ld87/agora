/**
 * Nachfragen an den Berichtsagenten (Etappe 5, #1804, Bauplan 4.6).
 *
 * Aufruf wie im Bestand (`Step5Interaction.vue`): `chatWithReport({ simulation_id,
 * message, chat_history })`, `chat_history` = bisherige Nachrichten als
 * `{ role: 'user' | 'assistant', content }` ohne die neue Frage. Die Antwort
 * kommt über `extractReportAnswer`; Fehlertexte über `interviewErrorMessage`
 * (Meldungen des Backends, z. B. Budget oder Ratenlimit, bleiben im Wortlaut
 * sichtbar). Anders als im Bestand gehen Fehler nicht als Assistentenantwort
 * in den Verlauf, und eine Antwort ohne Text ist ein Fehler, keine leere Antwort.
 *
 * Der Verlauf lebt je Lauf (`simulationId`) im Modul, solange die Sitzung
 * läuft; nichts wird gespeichert. Der Chat hängt am Lauf, nicht an der Fassung.
 */
import { computed, reactive, type ComputedRef } from 'vue'
import { ApiError } from '@/api/envelope'
import { chatWithReport } from '@/api/report'
import { extractReportAnswer, type ReportChatPayload } from '@/utils/reportChatAnswer'
import { interviewErrorMessage } from '@/utils/interviewErrorMessage'

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant' | 'error'
  content: string
}

const histories = reactive<Record<string, ChatMessage[]>>({})
const pending = reactive<Record<string, boolean>>({})
let nextId = 1

/** Nur für Tests: Sitzungszustand löschen. */
export function resetReportAgentChats(): void {
  for (const key of Object.keys(histories)) delete histories[key]
  for (const key of Object.keys(pending)) delete pending[key]
}

export interface UseReportAgentChatOptions {
  simulationId: () => string
  t: (key: string) => string
}

export function useReportAgentChat(options: UseReportAgentChatOptions): {
  messages: ComputedRef<ChatMessage[]>
  sending: ComputedRef<boolean>
  send: (text: string) => Promise<boolean>
  clear: () => void
} {
  const messages = computed(() => histories[options.simulationId()] ?? [])
  const sending = computed(() => pending[options.simulationId()] === true)

  async function send(text: string): Promise<boolean> {
    const message = text.trim()
    const id = options.simulationId()
    if (!message || pending[id]) return false
    const list = (histories[id] ??= [])
    const chatHistory = list
      .filter((m) => m.role !== 'error')
      .map((m) => ({ role: m.role, content: m.content }))
    list.push({ id: nextId++, role: 'user', content: message })
    pending[id] = true
    try {
      const res = await chatWithReport({ simulation_id: id, message, chat_history: chatHistory })
      if (!res || res.success !== true) {
        const failure = (res ?? {}) as { error?: unknown; code?: unknown }
        throw new ApiError({
          code: typeof failure.code === 'string' ? failure.code : '',
          status: 200,
          message: typeof failure.error === 'string' ? failure.error : '',
        })
      }
      const answer = extractReportAnswer(res.data as ReportChatPayload)
      if (answer) list.push({ id: nextId++, role: 'assistant', content: answer })
      else list.push({ id: nextId++, role: 'error', content: options.t('views.run.report.chat.noResponse') })
    } catch (err) {
      list.push({ id: nextId++, role: 'error', content: interviewErrorMessage(err, options.t) })
    } finally {
      pending[id] = false
    }
    return true
  }

  function clear(): void {
    delete histories[options.simulationId()]
  }

  return { messages, sending, send, clear }
}
