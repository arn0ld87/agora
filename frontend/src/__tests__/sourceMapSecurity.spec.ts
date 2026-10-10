import { describe, expect, it } from 'vitest'
import { SourceMapConsumer } from 'source-map-js'

function indexedMap(line: number) {
  return {
    version: '3', sources: [], names: [], mappings: '',
    sections: [{
      offset: { line, column: 0 },
      map: { version: '3', sources: ['input.js'], names: [], mappings: 'AAAA' },
    }],
  }
}

describe('CVE-2026-93749: indexed source-map offsets', () => {
  it('rejects extreme offsets before SourceNode can loop over them', () => {
    expect(() => new SourceMapConsumer(indexedMap(Number.MAX_SAFE_INTEGER)))
      .toThrow(/Section offset line must not exceed/)
  })

  it('still resolves a valid indexed source map', () => {
    const consumer = new SourceMapConsumer(indexedMap(0))
    expect(consumer.originalPositionFor({ line: 1, column: 1 }).source).toBe('input.js')
  })
})
