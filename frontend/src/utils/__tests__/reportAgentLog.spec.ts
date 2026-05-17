import { describe, expect, it } from 'vitest'
import { parseAgentEntry } from '../reportAgentLog'

describe('parseAgentEntry', () => {
  it('preserves visual log markers from the original Step4 renderer', () => {
    expect(parseAgentEntry({
      action: 'tool_call',
      tool_name: 'graph_search',
      details: { parameters: { query: 'x'.repeat(90) } },
    })?.title).toBe('TOOL → graph_search')
    expect(parseAgentEntry({
      action: 'tool_call',
      details: { parameters: { query: 'x'.repeat(90) } },
    })?.subtitle).toContain('…')
    expect(parseAgentEntry({ action: 'tool_result', tool_name: 'graph_search' })?.title).toBe('← graph_search')
    expect(parseAgentEntry({ action: 'section_start', section_index: 2, section_title: 'Kontext' })?.title).toBe('▶ Section 2: Kontext')
    expect(parseAgentEntry({ action: 'section_complete', section_index: 2 })?.title).toBe('✓ Section 2')
    expect(parseAgentEntry({ action: 'error', details: { message: 'kaputt' } })?.title).toBe('⚠ ERROR')
  })

  it('redacts sensitive tool parameters in the subtitle', () => {
    const secretMarker = 'PLAINTEXT_SECRET_VALUE'
    const entry = parseAgentEntry({
      action: 'tool_call',
      tool_name: 'http_get',
      details: {
        parameters: {
          url: 'https://example.com',
          api_token: secretMarker,
          Authorization: secretMarker,
          session_cookie: secretMarker,
          password: secretMarker,
          secret_key: secretMarker,
        },
      },
    })
    expect(entry?.subtitle).toContain('url=https://example.com')
    expect(entry?.subtitle).toContain('api_token=[redacted]')
    expect(entry?.subtitle).toContain('Authorization=[redacted]')
    expect(entry?.subtitle).toContain('session_cookie=[redacted]')
    expect(entry?.subtitle).toContain('password=[redacted]')
    expect(entry?.subtitle).toContain('secret_key=[redacted]')
    expect(entry?.subtitle).not.toContain(secretMarker)
  })
})
