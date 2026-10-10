import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const api = vi.hoisted(() => ({
  getGraphLock: vi.fn(),
  getGraphOntology: vi.fn(),
  createEntity: vi.fn(),
  updateEntity: vi.fn(),
  deleteEntity: vi.fn(),
  mergeEntities: vi.fn(),
  createRelation: vi.fn(),
  updateRelation: vi.fn(),
  deleteRelation: vi.fn(),
  duplicateGraph: vi.fn(),
  getGraphDuplicateRun: vi.fn(),
}))

vi.mock('@/api/graphEdit', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/graphEdit')>()
  return { ...actual, ...api }
})

import {
  GraphEditConflictError,
  GraphEditEmbeddingFailedError,
  GraphLockedError,
} from '@/api/graphEdit'
import GraphEditView from '../GraphEditView.vue'
import { GraphEditTestId } from '@/contracts/testIds'
import { buildReaderModel } from '@/composables/graph-library/graphReaderModel'
import {
  EDITED_EDGE,
  EXTRACTED_EDGE,
  EXTRACTED_NODE,
  MANUAL_NODE,
  SECOND_NODE,
  CanvasStub,
  editableGraphFixture,
  makeI18n,
  makeRouter,
} from './fixtures'

const sim = { simulation_id: 'sim_1', status: 'completed', project_id: 'p1', branch_name: null }

async function mountView(over: Record<string, unknown> = {}) {
  const data = editableGraphFixture()
  const router = makeRouter()
  await router.push('/graphs/proj_1')
  await router.isReady()
  const wrapper = mount(GraphEditView, {
    props: { model: buildReaderModel(data), graphData: data, notice: null, ...over },
    global: { plugins: [makeI18n(), router], stubs: { GraphCanvas: CanvasStub } },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset()
  api.getGraphLock.mockResolvedValue({ graph_id: editableGraphFixture().graph_id, locked: false, used_by: [] })
  api.getGraphOntology.mockResolvedValue({ ontology: null, entity_types: ['Person', 'Organization'] })
})

describe('GraphEditView', () => {
  it('fragt den Sperrzustand ab und nennt „Bearbeitbar“', async () => {
    const wrapper = await mountView()
    await flushPromises()
    expect(api.getGraphLock).toHaveBeenCalledWith(editableGraphFixture().graph_id)
    expect(wrapper.get(`[data-testid="${GraphEditTestId.lockBadge}"]`).text()).toBe('Bearbeitbar')
  })

  it('zeigt einen gesperrten Graphen als Band mit Grund und nennt den Weg über eine Kopie', async () => {
    api.getGraphLock.mockResolvedValue({ graph_id: editableGraphFixture().graph_id, locked: true, used_by: [sim] })
    const wrapper = await mountView()
    await flushPromises()
    const banner = wrapper.get(`[data-testid="${GraphEditTestId.lockBanner}"]`)
    expect(banner.text()).toContain('Eine Simulation verwendet diesen Graphen')
    expect(banner.get(`[data-testid="${GraphEditTestId.lockUsedBy}"]`).text()).toContain('sim_1')
    expect(wrapper.find(`[data-testid="${GraphEditTestId.toolbar}"]`).exists()).toBe(false)
    // Der Sperrzustand steht auch an der Bearbeitungsspalte, nicht nur im Band.
    expect(wrapper.find(`[data-testid="graph-edit-detail-readonly"]`).exists()).toBe(true)
  })

  it('schaltet zwischen Netz und Tabelle um und behält die Herkunftsmarken', async () => {
    const wrapper = await mountView()
    await flushPromises()
    expect(wrapper.find(`[data-testid="${GraphEditTestId.net}"]`).exists()).toBe(true)
    expect(wrapper.find(`[data-testid="${GraphEditTestId.table}"]`).exists()).toBe(false)
    // Das Netz bekommt beide Kanten, eine davon als Handkante gestrichelt.
    expect(wrapper.get('[data-testid="canvas-stub"]').attributes('data-dashed')).toBe('1')

    await wrapper.get(`[data-testid="${GraphEditTestId.viewTable}"]`).trigger('click')
    expect(wrapper.get(`[data-testid="${GraphEditTestId.table}"]`).find('table').exists()).toBe(true)
    expect(wrapper.get(`[data-testid="${GraphEditTestId.viewTable}"]`).attributes('aria-pressed')).toBe('true')

    await wrapper.get(`[data-testid="${GraphEditTestId.viewNet}"]`).trigger('click')
    expect(wrapper.find(`[data-testid="${GraphEditTestId.net}"]`).exists()).toBe(true)
  })

  it('trägt die Herkunftsmarke an Liste, Tabelle und Detail', async () => {
    const wrapper = await mountView()
    await flushPromises()
    expect(
      wrapper.find(`[data-entity-id="${MANUAL_NODE}"] [data-testid="${GraphEditTestId.markManual}"]`).exists(),
    ).toBe(true)
    expect(
      wrapper.find(`[data-entity-id="${EXTRACTED_NODE}"] [data-testid="${GraphEditTestId.markManual}"]`).exists(),
    ).toBe(false)

    await wrapper.get(`[data-entity-id="${MANUAL_NODE}"] button`).trigger('click')
    expect(wrapper.find(`aside [data-testid="${GraphEditTestId.markManual}"]`).exists()).toBe(true)

    await wrapper.get(`[data-testid="${GraphEditTestId.viewTable}"]`).trigger('click')
    await wrapper.get('#grt-tab-relations').trigger('click')
    const row = wrapper.get(`tr[data-edge-id="${EDITED_EDGE}"]`)
    expect(row.text()).toContain('bearbeitet')
    expect(wrapper.get(`tr[data-edge-id="${EXTRACTED_EDGE}"]`).text()).not.toContain('bearbeitet')
  })

  it('legt eine Entität von Hand an und meldet die Änderung nach außen', async () => {
    api.createEntity.mockResolvedValue({ uuid: MANUAL_NODE })
    const wrapper = await mountView()
    await flushPromises()
    await wrapper.get(`[data-testid="${GraphEditTestId.createEntity}"]`).trigger('click')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityName}"]`).setValue('Neuer Ort')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityType}"]`).setValue('Ort')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityForm}"]`).trigger('submit')
    await flushPromises()

    expect(api.createEntity).toHaveBeenCalledWith(
      editableGraphFixture().graph_id,
      expect.objectContaining({ name: 'Neuer Ort', entity_type: 'Ort' }),
    )
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.get(`[data-testid="${GraphEditTestId.notice}"]`).text()).toContain('Gespeichert')
  })

  it('legt eine Beziehung von Hand an', async () => {
    api.createRelation.mockResolvedValue({ uuid: EDITED_EDGE })
    const wrapper = await mountView()
    await flushPromises()
    await wrapper.get(`[data-testid="${GraphEditTestId.createRelation}"]`).trigger('click')
    await wrapper.get(`[data-testid="${GraphEditTestId.relationSource}"]`).setValue(EXTRACTED_NODE)
    await wrapper.get(`[data-testid="${GraphEditTestId.relationTarget}"]`).setValue(MANUAL_NODE)
    await wrapper.get(`[data-testid="${GraphEditTestId.relationName}"]`).setValue('ARBEITET_IN')
    await wrapper.get(`[data-testid="${GraphEditTestId.relationFact}"]`).setValue('Sitzt dort.')
    await wrapper.get(`[data-testid="${GraphEditTestId.relationForm}"]`).trigger('submit')
    await flushPromises()

    expect(api.createRelation).toHaveBeenCalledWith(
      editableGraphFixture().graph_id,
      expect.objectContaining({ source_uuid: EXTRACTED_NODE, target_uuid: MANUAL_NODE }),
    )
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('löscht eine Entität erst nach der Rückfrage und meldet die Änderung', async () => {
    api.deleteEntity.mockResolvedValue({ uuid: SECOND_NODE, removed_relation_count: 2 })
    const wrapper = await mountView()
    await flushPromises()
    await wrapper.get(`[data-entity-id="${SECOND_NODE}"] button`).trigger('click')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityDelete}"]`).trigger('click')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityDeleteConfirm}"]`).trigger('click')
    await flushPromises()

    expect(api.deleteEntity).toHaveBeenCalledWith(editableGraphFixture().graph_id, SECOND_NODE)
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.get(`[data-testid="${GraphEditTestId.notice}"]`).text()).toContain('2 Beziehungen')
  })

  it('führt zwei Entitäten zusammen und nennt die Zahl umgehängter Beziehungen', async () => {
    api.mergeEntities.mockResolvedValue({
      target: { uuid: EXTRACTED_NODE },
      merged_source_uuids: [SECOND_NODE],
      rewired_relation_count: 2,
      dropped_relation_count: 1,
    })
    const wrapper = await mountView()
    await flushPromises()
    await wrapper.get(`[data-entity-id="${EXTRACTED_NODE}"] button`).trigger('click')
    await wrapper.get(`[data-testid="${GraphEditTestId.mergeOpen}"]`).trigger('click')
    await wrapper.findAll(`[data-testid="${GraphEditTestId.mergeSource}"]`)[0]!.setValue(true)
    await wrapper.get(`[data-testid="${GraphEditTestId.mergeSubmit}"]`).trigger('click')
    await flushPromises()

    expect(api.mergeEntities).toHaveBeenCalledWith(editableGraphFixture().graph_id, {
      target_uuid: EXTRACTED_NODE,
      source_uuids: [SECOND_NODE],
    })
    expect(wrapper.get(`[data-testid="${GraphEditTestId.notice}"]`).text()).toContain('2 Beziehungen')
  })

  it('zeigt 409 Sperre als Sperre im Band und als Fehler, und schreibt nichts weiter', async () => {
    const wrapper = await mountView()
    await flushPromises()
    api.createEntity.mockRejectedValue(new GraphLockedError('gesperrt', [sim]))
    await wrapper.get(`[data-testid="${GraphEditTestId.createEntity}"]`).trigger('click')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityName}"]`).setValue('Neu')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityType}"]`).setValue('Ort')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityForm}"]`).trigger('submit')
    await flushPromises()

    expect(wrapper.get(`[data-testid="${GraphEditTestId.errorLocked}"]`).text()).toContain('gesperrt')
    expect(wrapper.get(`[data-testid="${GraphEditTestId.lockBanner}"]`).text()).toContain('sim_1')
    expect(wrapper.emitted('changed')).toBeUndefined()
    expect(wrapper.find(`[data-testid="${GraphEditTestId.toolbar}"]`).exists()).toBe(false)
  })

  it('unterscheidet 409 Konflikt und 503 Einbettung im Text', async () => {
    const wrapper = await mountView()
    await flushPromises()

    api.createEntity.mockRejectedValueOnce(new GraphEditConflictError('doppelt'))
    await wrapper.get(`[data-testid="${GraphEditTestId.createEntity}"]`).trigger('click')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityName}"]`).setValue('Neu')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityType}"]`).setValue('Ort')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityForm}"]`).trigger('submit')
    await flushPromises()
    expect(wrapper.get(`[data-testid="${GraphEditTestId.errorConflict}"]`).text()).toContain('kollidiert')

    await wrapper.get(`[data-testid="${GraphEditTestId.error}"] button`).trigger('click')
    api.createEntity.mockRejectedValueOnce(new GraphEditEmbeddingFailedError('kein embedding'))
    await wrapper.get(`[data-testid="${GraphEditTestId.entityForm}"]`).trigger('submit')
    await flushPromises()
    expect(wrapper.get(`[data-testid="${GraphEditTestId.errorEmbeddingFailed}"]`).text()).toContain('Einbettung')
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

  it('bietet bei gesperrtem Graphen den Ausweg über eine Kopie an und startet ihn', async () => {
    api.getGraphLock.mockResolvedValue({ graph_id: editableGraphFixture().graph_id, locked: true, used_by: [sim] })
    api.duplicateGraph.mockResolvedValue({
      run_id: 'run_dup_1',
      source_graph_id: editableGraphFixture().graph_id,
      graph_id: '22222222-2222-4222-8222-222222222299',
      project_id: 'proj_kopie',
      status: 'pending',
      progress: 0,
      message: 'Kopie angelegt',
      error: null,
    })
    const wrapper = await mountView({ graphName: 'Kreistag Moorhagen' })
    await flushPromises()

    const name = wrapper.get(`[data-testid="${GraphEditTestId.duplicateName}"]`)
    expect((name.element as HTMLInputElement).value).toBe('Kreistag Moorhagen')
    await wrapper.get(`[data-testid="${GraphEditTestId.duplicateStart}"]`).trigger('click')
    await flushPromises()

    expect(api.duplicateGraph).toHaveBeenCalledWith(editableGraphFixture().graph_id, {
      name: 'Kreistag Moorhagen',
    })
    const state = wrapper.get(`[data-testid="${GraphEditTestId.duplicateState}"]`)
    expect(state.attributes('data-status')).toBe('pending')
    // Ein laufender Auftrag ist noch keine Kopie: kein Ziel, kein `changed`.
    expect(wrapper.find(`[data-testid="${GraphEditTestId.duplicateOpen}"]`).exists()).toBe(false)
    expect(wrapper.emitted('changed')).toBeUndefined()
    wrapper.unmount()
  })

  it('schlägt ohne Anzeigamen auf die graph_id zurück, statt einen leeren Namen zu senden', async () => {
    api.getGraphLock.mockResolvedValue({ graph_id: editableGraphFixture().graph_id, locked: true, used_by: [sim] })
    api.duplicateGraph.mockResolvedValue({
      run_id: 'run_dup_1',
      graph_id: 'g2',
      project_id: 'proj_kopie',
      status: 'pending',
      progress: 0,
      message: '',
      error: null,
    })
    const wrapper = await mountView()
    await flushPromises()
    await wrapper.get(`[data-testid="${GraphEditTestId.duplicateStart}"]`).trigger('click')
    await flushPromises()

    expect(api.duplicateGraph).toHaveBeenCalledWith(editableGraphFixture().graph_id, {
      name: editableGraphFixture().graph_id,
    })
    wrapper.unmount()
  })

  it('bei gesperrtem Graphen bleibt das Schreibwerkzeug weg', async () => {
    api.getGraphLock.mockResolvedValue({ graph_id: editableGraphFixture().graph_id, locked: true, used_by: [sim] })
    const wrapper = await mountView()
    await flushPromises()
    expect(wrapper.find(`[data-testid="${GraphEditTestId.toolbar}"]`).exists()).toBe(false)
    // Der Ausweg ist dafuer vorhanden.
    expect(wrapper.find(`[data-testid="${GraphEditTestId.duplicateStart}"]`).exists()).toBe(true)
    wrapper.unmount()
  })

  it('während einer laufenden Änderung sind die Felder gesperrt', async () => {
    // Die Zusage bleibt offen, bis der Test sie am Ende aufloest.
    let release: (value: unknown) => void = () => undefined
    api.updateEntity.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = resolve
        }) as Promise<unknown>,
    )
    const wrapper = await mountView()
    await flushPromises()
    await wrapper.get(`[data-entity-id="${EXTRACTED_NODE}"] button`).trigger('click')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityName}"]`).setValue('Neu')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityForm}"]`).trigger('submit')
    await wrapper.vm.$nextTick()

    expect(wrapper.get(`[data-testid="${GraphEditTestId.entityName}"]`).attributes('disabled')).toBeDefined()
    release({ uuid: EXTRACTED_NODE })
    await flushPromises()
  })

  // Abnahme Etappe 8 (Evidenzlücken): Sperre ohne Schreibweg, Herkunft unabhängig
  // von der Sperre, fail-closed bei unklarem Sperrzustand, Bedienung und Namen.
  describe('Abnahme Etappe 8', () => {
    async function mountLocked() {
      api.getGraphLock.mockResolvedValue({ graph_id: editableGraphFixture().graph_id, locked: true, used_by: [sim] })
      const wrapper = await mountView()
      await flushPromises()
      return wrapper
    }

    it('gesperrt: Auswahl zeigt nur lesbare Details, kein Formular, kein Löschen, kein Zusammenführen', async () => {
      const wrapper = await mountLocked()
      await wrapper.get(`[data-entity-id="${MANUAL_NODE}"] button`).trigger('click')
      const note = wrapper.get('[data-testid="graph-edit-detail-readonly"]')
      expect(note.attributes('role')).toBe('status')
      expect(note.text()).toContain('gesperrt und nicht bearbeitbar')
      for (const id of [
        GraphEditTestId.createEntity,
        GraphEditTestId.createRelation,
        GraphEditTestId.entityForm,
        GraphEditTestId.entityName,
        GraphEditTestId.entityDelete,
        GraphEditTestId.mergeOpen,
      ]) {
        expect(wrapper.find(`[data-testid="${id}"]`).exists()).toBe(false)
      }
      for (const fn of [api.createEntity, api.updateEntity, api.deleteEntity, api.mergeEntities, api.createRelation, api.updateRelation, api.deleteRelation]) {
        expect(fn).not.toHaveBeenCalled()
      }
      wrapper.unmount()
    })

    it('gesperrt: Band nennt Zustand, Grund und Ausweg als Statusmeldung', async () => {
      const wrapper = await mountLocked()
      const banner = wrapper.get(`[data-testid="${GraphEditTestId.lockBanner}"]`)
      expect(banner.attributes('role')).toBe('status')
      expect(wrapper.get(`[data-testid="${GraphEditTestId.lockBadge}"]`).text()).toContain('Gesperrt')
      expect(banner.text()).toContain('Zum Bearbeiten eine unabhängige Kopie anlegen')
      expect(wrapper.get(`[data-testid="${GraphEditTestId.duplicateStart}"]`).text()).toBe('Kopie anlegen')
      wrapper.unmount()
    })

    it('gesperrt: die Herkunftsmarken bleiben sichtbar, auch die Handkante im Netz', async () => {
      const wrapper = await mountLocked()
      expect(
        wrapper.find(`[data-entity-id="${MANUAL_NODE}"] [data-testid="${GraphEditTestId.markManual}"]`).text(),
      ).toContain('manuell')
      expect(wrapper.get('[data-testid="canvas-stub"]').attributes('data-dashed')).toBe('1')
      wrapper.unmount()
    })

    it('Herkunft: extrahierte Knoten tragen in der Liste keine Marke, die Legende erklärt die gestrichelte Kante', async () => {
      const wrapper = await mountView()
      await flushPromises()
      const extracted = wrapper.get(`[data-entity-id="${EXTRACTED_NODE}"]`)
      expect(extracted.find(`[data-testid="${GraphEditTestId.markManual}"]`).exists()).toBe(false)
      expect(extracted.find(`[data-testid="${GraphEditTestId.markEdited}"]`).exists()).toBe(false)
      expect(wrapper.text()).toContain('Gestrichelte Kante: von Hand angelegt oder von Hand geändert.')
      wrapper.unmount()
    })

    it('unklarer Sperrzustand: fail-closed, Meldung als Alert, kein Schreibwerkzeug', async () => {
      api.getGraphLock.mockRejectedValue(new Error('lock down'))
      const wrapper = await mountView()
      await flushPromises()
      expect(wrapper.get(`[data-testid="${GraphEditTestId.lockBanner}"]`).attributes('role')).toBe('alert')
      expect(wrapper.get('[data-testid="graph-edit-lock-reload"]').text()).toBe('Sperrzustand neu laden')
      expect(wrapper.find(`[data-testid="${GraphEditTestId.toolbar}"]`).exists()).toBe(false)
      expect(wrapper.find(`[data-testid="${GraphEditTestId.createEntity}"]`).exists()).toBe(false)
      wrapper.unmount()
    })

    it('Löschen: Rückfrage allein löst nichts aus, erst die Bestätigung ruft deleteEntity', async () => {
      const wrapper = await mountView()
      await flushPromises()
      await wrapper.get(`[data-entity-id="${SECOND_NODE}"] button`).trigger('click')
      await wrapper.get(`[data-testid="${GraphEditTestId.entityDelete}"]`).trigger('click')
      expect(wrapper.find(`[data-testid="${GraphEditTestId.entityDeleteConfirm}"]`).exists()).toBe(true)
      expect(api.deleteEntity).not.toHaveBeenCalled()
      wrapper.unmount()
    })

    it('Bedienung: Liste und Umschalter sind benannte Schaltflächen mit Zustand', async () => {
      const wrapper = await mountView()
      await flushPromises()
      const select = wrapper.get(`[data-entity-id="${SECOND_NODE}"] button`)
      expect(select.element.tagName).toBe('BUTTON')
      await select.trigger('click')
      expect(select.attributes('aria-current')).toBe('true')
      const group = wrapper.get(`[data-testid="${GraphEditTestId.viewToggle}"]`)
      expect(group.attributes('role')).toBe('group')
      expect(group.attributes('aria-label')).toBe('Graph bearbeiten')
      expect(wrapper.get(`[data-testid="${GraphEditTestId.viewNet}"]`).text()).toBe('Netz')
      expect(wrapper.get(`[data-testid="${GraphEditTestId.viewTable}"]`).text()).toBe('Tabelle')
      expect(wrapper.get(`[data-testid="${GraphEditTestId.viewNet}"]`).attributes('aria-pressed')).toBe('true')
      expect(wrapper.get('section').attributes('aria-label')).toBe('Graph bearbeiten')
      wrapper.unmount()
    })

    it('Bedienung: die Felder des Entitätsformulars sind über Beschriftungen benannt', async () => {
      const wrapper = await mountView()
      await flushPromises()
      await wrapper.get(`[data-testid="${GraphEditTestId.createEntity}"]`).trigger('click')
      const labelOf = (testId: string) => {
        const el = wrapper.get(`[data-testid="${testId}"]`).element
        const wrapped = el.closest('label')?.textContent ?? ''
        const byFor = el.id ? (wrapper.find(`label[for="${el.id}"]`).exists() ? wrapper.get(`label[for="${el.id}"]`).text() : '') : ''
        return `${wrapped} ${byFor} ${el.getAttribute('aria-label') ?? ''}`
      }
      expect(labelOf(GraphEditTestId.entityName)).toContain('Name')
      expect(labelOf(GraphEditTestId.entityType)).toContain('Typ')
      wrapper.unmount()
    })
  })
})
