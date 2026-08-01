import { describe, expect, it } from 'vitest'

import { extractReportAnswer } from '../reportChatAnswer'

describe('extractReportAnswer', () => {
  it('packt den verschachtelten ReportAgent-Payload aus', () => {
    const data = {
      response: {
        response: 'Die Belegschaft reagiert skeptisch.',
        tool_calls: [{ name: 'search_graph' }],
        sources: ['Schichtmodell'],
      },
    }

    expect(extractReportAnswer(data)).toBe('Die Belegschaft reagiert skeptisch.')
  })

  it('akzeptiert weiterhin eine flache String-Antwort', () => {
    expect(extractReportAnswer({ response: 'Direkt als String' })).toBe('Direkt als String')
  })

  it('faellt auf answer und message zurueck', () => {
    expect(extractReportAnswer({ answer: 'aus answer' })).toBe('aus answer')
    expect(extractReportAnswer({ message: 'aus message' })).toBe('aus message')
  })

  it('nutzt aeussere Legacy-Felder, wenn response kein Textfeld hat', () => {
    expect(extractReportAnswer({ response: { tool_calls: [] }, answer: 'aus answer' })).toBe(
      'aus answer',
    )
    expect(extractReportAnswer({ response: { sources: [] }, message: 'aus message' })).toBe(
      'aus message',
    )
  })

  it('liefert leeren String statt eines Objekts', () => {
    expect(extractReportAnswer({ response: { tool_calls: [] } })).toBe('')
    expect(extractReportAnswer({})).toBe('')
    expect(extractReportAnswer(null)).toBe('')
  })
})
