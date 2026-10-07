import { describe, expect, it } from 'vitest'
import { deriveOutline, deriveReading } from '../reportSections'
import { reportData } from './reportFixtures'

const outline = reportData().outline!

describe('deriveOutline', () => {
  it('ready / missing / failed / pending und überzählige fehlende Abschnitte', () => {
    const entries = deriveOutline({
      outline,
      evidenceSections: [],
      missingSections: ['akteure ', 'Hypothesen'],
      generatedSections: { '1': { content: 'x', generation_failed: true } },
      reportStatus: 'generating',
    })
    expect(entries.map((e) => [e.index, e.title, e.state])).toEqual([
      [1, 'Risiken', 'failed'],
      [2, 'Akteure', 'missing'],
      [3, 'Hypothesen', 'missing'],
    ])
  })

  it('laufend ohne Text: pending; terminal ohne Text je Abschnitt: ready', () => {
    const base = { outline, evidenceSections: [], missingSections: [], generatedSections: {} }
    expect(deriveOutline({ ...base, reportStatus: 'generating' }).map((e) => e.state)).toEqual(['pending', 'pending'])
    expect(deriveOutline({ ...base, reportStatus: 'completed' }).map((e) => e.state)).toEqual(['ready', 'ready'])
  })
})

describe('deriveReading', () => {
  it('ohne Text je Abschnitt: ein Block, sanitisiert', () => {
    const r = deriveReading({
      outline, evidenceSections: [], missingSections: [], generatedSections: {}, reportStatus: 'completed',
      markdownContent: 'a <script>x</script> **b**', fallbackTitle: 'Bericht',
    })
    expect(r.mode).toBe('whole')
    expect(r.wholeHtml).not.toContain('<script')
    expect(r.wholeHtml).toContain('<strong>b</strong>')
    expect(r.title).toBe('Branche und Abgabe')
  })

  it('mit Text je Abschnitt: sections-Modus', () => {
    const r = deriveReading({
      outline, evidenceSections: [], missingSections: [], reportStatus: 'generating',
      generatedSections: { '1': { content: '**eins**' } }, markdownContent: '', fallbackTitle: 'Bericht',
    })
    expect(r.mode).toBe('sections')
    expect(r.sections[0]!.html).toContain('<strong>eins</strong>')
    expect(r.sections[1]!.html).toBe('')
  })
})
