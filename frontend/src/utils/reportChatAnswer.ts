/**
 * Antworttext aus der /api/report/chat-Envelope auspacken.
 *
 * Das Backend liefert `data.response` als ReportAgent-Payload
 * (`{ response, tool_calls, sources }`), nicht als String. Wird das Objekt
 * ungeprüft in den Chat gelegt, rendert Vue es als "[object Object]".
 * Ältere Antwortformen (`answer`, `message`, flacher String) bleiben unterstützt.
 */
export interface ReportChatPayload {
  response?: unknown
  answer?: unknown
  message?: unknown
}

function asText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

export function extractReportAnswer(data: ReportChatPayload | null | undefined): string {
  if (!data) return ''

  const payload = data.response
  if (typeof payload === 'string') return payload

  const nested = payload && typeof payload === 'object' ? (payload as ReportChatPayload) : null

  // Reihenfolge: verschachtelter Payload zuerst, dann die aeusseren
  // Legacy-Felder. Ein Objekt ohne Textfeld darf die Kette nicht abbrechen —
  // sonst geht ein daneben liegendes data.answer verloren.
  return (
    asText(nested?.response) ||
    asText(nested?.answer) ||
    asText(nested?.message) ||
    asText(data.answer) ||
    asText(data.message)
  )
}
