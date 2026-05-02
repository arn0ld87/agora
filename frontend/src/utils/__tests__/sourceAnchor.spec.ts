import { describe, it, expect } from 'vitest'
import { parseSourceAnchor, entryAnchorId } from '../sourceAnchor'

describe('parseSourceAnchor', () => {
  it('parses agent-log with entry', () => {
    expect(parseSourceAnchor('agent-log-42#entry-p1234')).toEqual({
      kind: 'agent-log', logId: '42', entryId: 'p1234',
    })
  })
  it('parses agent-log without entry', () => {
    expect(parseSourceAnchor('agent-log-42')).toEqual({
      kind: 'agent-log', logId: '42', entryId: null,
    })
  })
  it('parses web url', () => {
    expect(parseSourceAnchor('web:https://example.com/x')).toEqual({
      kind: 'web', url: 'https://example.com/x',
    })
  })
  it('parses web url with text-fragment', () => {
    expect(parseSourceAnchor('web:https://example.com/x#:~:text=Snippet')).toEqual({
      kind: 'web', url: 'https://example.com/x#:~:text=Snippet',
    })
  })
  it('parses kg anchor', () => {
    expect(parseSourceAnchor('kg:entity:9b2f-uuid')).toEqual({
      kind: 'kg', payload: 'entity:9b2f-uuid',
    })
  })
  it('returns unknown for free-form string', () => {
    expect(parseSourceAnchor('something else')).toEqual({
      kind: 'unknown', raw: 'something else',
    })
  })
  it('returns null for null/empty input', () => {
    expect(parseSourceAnchor(null)).toBeNull()
    expect(parseSourceAnchor('')).toBeNull()
  })
})

describe('entryAnchorId', () => {
  it('builds deterministic id from agent-log entry', () => {
    const entry = { timestamp: '2026-05-02T18:55:30Z', action: 'tool_call', tool_name: 'web_search', section_index: 1 }
    const id1 = entryAnchorId(entry)
    const id2 = entryAnchorId({ ...entry })
    expect(id1).toBe(id2)
    expect(id1).toContain('tool_call')
    expect(id1).toContain('web_search')
  })

  it('returns unknown for empty entry', () => {
    expect(entryAnchorId(null)).toBe('unknown')
    expect(entryAnchorId({})).toBe('unknown')
  })
})
