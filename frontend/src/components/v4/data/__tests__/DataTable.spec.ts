/**
 * DataTable — Tests
 * Slice D · 2026-05-11
 *
 * Test 1 (Smoke): rendert Columns + Rows korrekt
 * Test 2: Sticky-Header-Klasse gesetzt wenn sticky=true
 * Test 3: Empty-Slot greift wenn rows=[]
 * Test 4: rowClick wird mit Row-Object aufgerufen
 * Test 5: Custom-Cell-Slot überschreibt Default-Renderer
 * Test 6-9 (PR 5, Control-Primitives): label-Typo im Spaltenkopf, Selected-
 * Zustand über aria-current, Mono-Familie an col.mono statt an Ausrichtung.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import DataTable from '../DataTable.vue'
import type { DataTableColumn } from '../DataTable.vue'

const here = dirname(fileURLToPath(import.meta.url))

const columns: DataTableColumn[] = [
  { key: 'stage', label: 'Stage', mono: true },
  { key: 'provider', label: 'Provider', secondary: true },
  { key: 'status', label: 'Status' },
]

const rows = [
  { id: '1', stage: 'document_ingest', provider: 'openai', status: 'Completed' },
  { id: '2', stage: 'graph_build', provider: 'google', status: 'Running' },
]

describe('DataTable', () => {
  it('Test 1: rendert Columns + Rows korrekt', () => {
    const wrapper = mount(DataTable, {
      props: { columns, rows },
    })

    // Alle Column-Labels im Header
    expect(wrapper.find('th').text()).toBe('Stage')
    const ths = wrapper.findAll('th')
    expect(ths).toHaveLength(3)
    expect(ths[0].text()).toBe('Stage')
    expect(ths[1].text()).toBe('Provider')
    expect(ths[2].text()).toBe('Status')

    // Alle Rows gerendert
    const bodyRows = wrapper.findAll('tbody tr')
    expect(bodyRows).toHaveLength(2)

    // Zellinhalte
    expect(bodyRows[0].text()).toContain('document_ingest')
    expect(bodyRows[0].text()).toContain('openai')
    expect(bodyRows[0].text()).toContain('Completed')
    expect(bodyRows[1].text()).toContain('graph_build')
  })

  it('Test 2: Sticky-Header-Klasse gesetzt wenn sticky=true (default)', () => {
    const wrapper = mount(DataTable, {
      props: { columns, rows },
    })
    // sticky default true → thead hat sticky-Klasse
    expect(wrapper.find('thead').classes()).toContain('dt-thead--sticky')
  })

  it('Test 2b: kein Sticky-Header wenn sticky=false', () => {
    const wrapper = mount(DataTable, {
      props: { columns, rows, sticky: false },
    })
    expect(wrapper.find('thead').classes()).not.toContain('dt-thead--sticky')
  })

  it('Test 3: Empty-Slot greift wenn rows=[]', () => {
    const wrapper = mount(DataTable, {
      props: { columns, rows: [] },
    })
    // Default-Empty-Text
    expect(wrapper.text()).toContain('Keine Daten')

    // Nur 1 tbody-Row (colspan-Zeile)
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
  })

  it('Test 3b: Custom Empty-Slot wird gerendert', () => {
    const wrapper = mount(DataTable, {
      props: { columns, rows: [] },
      slots: {
        empty: '<span data-testid="custom-empty">Leer!</span>',
      },
    })
    expect(wrapper.find('[data-testid="custom-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="custom-empty"]').text()).toBe('Leer!')
  })

  it('Test 4: rowClick wird mit Row-Object aufgerufen', async () => {
    const onClick = vi.fn()
    const wrapper = mount(DataTable, {
      props: { columns, rows, rowClick: onClick },
    })

    const firstRow = wrapper.findAll('tbody tr')[0]
    expect(firstRow.classes()).toContain('dt-body-row--clickable')

    await firstRow.trigger('click')
    expect(onClick).toHaveBeenCalledOnce()
    expect(onClick).toHaveBeenCalledWith(rows[0])
  })

  it('Test 5: Custom-Cell-Slot überschreibt Default-Renderer', () => {
    const wrapper = mount(DataTable, {
      props: { columns, rows },
      slots: {
        'cell-status': `<template #cell-status="{ value }">
          <span data-testid="custom-status">STATUS:{{ value }}</span>
        </template>`,
      },
    })

    const customCells = wrapper.findAll('[data-testid="custom-status"]')
    // 2 Rows → 2 Custom-Cells
    expect(customCells).toHaveLength(2)
    expect(customCells[0].text()).toBe('STATUS:Completed')
    expect(customCells[1].text()).toBe('STATUS:Running')
  })

  it('Test 6: Spaltenkopf trägt kein text-transform:uppercase mehr (Audit §Typografie)', () => {
    // Regressionstest zu PR 5: .dt-th nutzt die label-Typo-Rolle (Satzschrift,
    // kein Uppercase). Geprüft wird der SFC-Quelltext, nicht getComputedStyle —
    // jsdom wendet scoped SFC-Styles nicht an, ein Stilvergleich am gemounteten
    // Element würde immer bestehen und nichts absichern.
    const sfc = readFileSync(resolve(here, '../DataTable.vue'), 'utf8')
    const thBlock = sfc.match(/\.dt-th\s*\{[^}]*\}/)
    expect(thBlock).not.toBeNull()
    expect(thBlock![0]).not.toMatch(/text-transform:\s*uppercase/)
  })

  it('Test 7: rowSelected markiert die Zeile mit Marker-Klasse und aria-current', () => {
    // aria-current statt aria-selected: aria-selected ist auf <tr> nur in einem
    // role="grid"/"treegrid" zulässig, diese Tabelle ist eine schlichte
    // role="table" — axe-core aria-allowed-attr würde das rügen.
    const wrapper = mount(DataTable, {
      props: { columns, rows, rowSelected: (row: Record<string, unknown>) => row.id === '1' },
    })
    const bodyRows = wrapper.findAll('tbody tr')

    expect(bodyRows[0].classes()).toContain('dt-body-row--selected')
    expect(bodyRows[0].attributes('aria-current')).toBe('true')
    expect(bodyRows[1].classes()).not.toContain('dt-body-row--selected')
    expect(bodyRows[1].attributes('aria-current')).toBeUndefined()
  })

  it('Test 8: ohne rowSelected-Prop bleibt aria-current unbesetzt', () => {
    const wrapper = mount(DataTable, { props: { columns, rows } })
    const firstRow = wrapper.findAll('tbody tr')[0]
    expect(firstRow.attributes('aria-current')).toBeUndefined()
  })

  it('Test 9: die Mono-Familie hängt an col.mono, nicht an rechtsbündiger Ausrichtung', () => {
    // Rechtsbündig heißt nicht zwangsläufig numerisch (z. B. eine rechts
    // ausgerichtete Textspalte), und der Spaltenkopf bleibt in der label-Typo.
    const sfc = readFileSync(resolve(here, '../DataTable.vue'), 'utf8')
    const rightBlock = sfc.match(/\.dt-cell--right\s*\{[^}]*\}/)
    expect(rightBlock).not.toBeNull()
    expect(rightBlock![0]).not.toMatch(/font-family/)
    expect(rightBlock![0]).toMatch(/font-variant-numeric:\s*tabular-nums/)
    expect(sfc).toMatch(/\.dt-td--mono\s*\{[^}]*font-family:\s*var\(--font-mono\)/)
  })
})
