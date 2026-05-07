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
})
