import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import GraphEditDetail from '../GraphEditDetail.vue'
import { GraphEditTestId } from '@/contracts/testIds'
import { buildReaderModel } from '@/composables/graph-library/graphReaderModel'
import type { ReaderEntity, ReaderRelation } from '@/composables/graph-library/graphReaderModel'
import { EDITED_EDGE, EXTRACTED_NODE, MANUAL_NODE, SECOND_NODE, editableGraphFixture, makeI18n } from './fixtures'

const model = buildReaderModel(editableGraphFixture())
const entities = model.entities
const relations = model.relations

function findEntity(id: string): ReaderEntity {
  const hit = entities.find((e) => e.id === id)
  if (!hit) throw new Error(`fehlt: ${id}`)
  return hit
}

function findRelation(id: string): ReaderRelation {
  const hit = relations.find((r) => r.id === id)
  if (!hit) throw new Error(`fehlt: ${id}`)
  return hit
}

/** Der Wert eines Formularfelds; der Wrapper liefert typisiert nur `Element`. */
function fieldValue(within: { get: (selector: string) => { element: unknown } }, testId: string): string {
  return (within.get(`[data-testid="${testId}"]`).element as HTMLInputElement).value
}

function mountDetail(over: Record<string, unknown> = {}) {
  return mount(GraphEditDetail, {
    props: {
      entity: null,
      relation: null,
      entities,
      relations,
      editable: true,
      busy: false,
      mode: 'view',
      ...over,
    },
    global: { plugins: [makeI18n()] },
  })
}

describe('GraphEditDetail', () => {
  it('zeigt ohne Auswahl den Hinweis und nichts zum Bearbeiten', () => {
    const wrapper = mountDetail()
    expect(wrapper.text()).toContain('Entität wählen')
    expect(wrapper.find(`[data-testid="${GraphEditTestId.entityForm}"]`).exists()).toBe(false)
  })

  it('trägt die Herkunftsmarke der gewählten Entität und öffnet das Formular', () => {
    const wrapper = mountDetail({ entity: findEntity(MANUAL_NODE) })
    expect(wrapper.get(`[data-testid="${GraphEditTestId.markManual}"]`).text()).toContain('manuell')

    const form = wrapper.get(`[data-testid="${GraphEditTestId.entityForm}"]`)
    expect(fieldValue(form, GraphEditTestId.entityName)).toBe('Neues Buero')
    expect(fieldValue(form, GraphEditTestId.entityType)).toBe('Organisation')
    expect(fieldValue(form, GraphEditTestId.entitySummary)).toBe('von Hand angelegt')
  })

  it('sendet nur die geänderten Felder einer Entität', async () => {
    const wrapper = mountDetail({ entity: findEntity(EXTRACTED_NODE) })
    await wrapper.get(`[data-testid="${GraphEditTestId.entityName}"]`).setValue('Kreistag neu')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityForm}"]`).trigger('submit')

    expect(wrapper.emitted('update-entity')).toEqual([
      [EXTRACTED_NODE, { name: 'Kreistag neu' }],
    ])
  })

  it('schickt Aliase getrennt und leer als leeres Feld', async () => {
    const wrapper = mountDetail({ entity: findEntity(EXTRACTED_NODE) })
    expect(fieldValue(wrapper, GraphEditTestId.entityAliases)).toBe('Kreisrat')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityAliases}"]`).setValue('Kreisrat, Rat, Kreisrat')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityForm}"]`).trigger('submit')

    const [uuid, patch] = wrapper.emitted('update-entity')![0] as [string, Record<string, unknown>]
    expect(uuid).toBe(EXTRACTED_NODE)
    expect(patch).toEqual({ aliases: ['Kreisrat', 'Rat'] })
  })

  it('fragt vor dem Löschen einer Entität nach und sendet erst dann', async () => {
    const wrapper = mountDetail({ entity: findEntity(EXTRACTED_NODE) })
    await wrapper.get(`[data-testid="${GraphEditTestId.entityDelete}"]`).trigger('click')
    expect(wrapper.emitted('delete-entity')).toBeUndefined()
    expect(wrapper.get(`[data-testid="${GraphEditTestId.entityDeleteConfirm}"]`).text()).toContain('löschen')

    await wrapper.get(`[data-testid="${GraphEditTestId.entityDeleteConfirm}"]`).trigger('click')
    expect(wrapper.emitted('delete-entity')).toEqual([[EXTRACTED_NODE]])
  })

  it('schickt beim Anlegen Name, Typ und Aliase, ohne uuid', async () => {
    const wrapper = mountDetail({ mode: 'create-entity' })
    await wrapper.get(`[data-testid="${GraphEditTestId.entityName}"]`).setValue('Neuer Ort')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityType}"]`).setValue('Ort')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityAliases}"]`).setValue('Dorf')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityForm}"]`).trigger('submit')

    expect(wrapper.emitted('create-entity')).toEqual([
      [{ name: 'Neuer Ort', entity_type: 'Ort', aliases: ['Dorf'] }],
    ])
  })

  it('bietet Typen aus der Ontologie im Typauswahl-Feld an', () => {
    const wrapper = mountDetail({ mode: 'create-entity', ontologyTypes: ['SpezialRolle', 'Ort'] })
    const form = wrapper.get(`[data-testid="${GraphEditTestId.entityForm}"]`)
    const options = form.get(`[data-testid="${GraphEditTestId.entityType}"]`).findAll('option')
    expect(options.map((o) => o.text())).toContain('SpezialRolle')
  })

  it('verlangt beim Anlegen von Hand eine Typauswahl und einen Namen', async () => {
    const wrapper = mountDetail({ mode: 'create-entity' })
    const submit = wrapper.get(`[data-testid="${GraphEditTestId.entitySubmit}"]`)
    expect(submit.attributes('disabled')).toBeDefined()

    await wrapper.get(`[data-testid="${GraphEditTestId.entityName}"]`).setValue('Nur Name')
    expect(submit.attributes('disabled')).toBeDefined()

    await wrapper.get(`[data-testid="${GraphEditTestId.entityType}"]`).setValue('Ort')
    expect(wrapper.get(`[data-testid="${GraphEditTestId.entitySubmit}"]`).attributes('disabled')).toBeUndefined()
  })

  it('zeigt beim Anlegen einer Beziehung Quell-, Ziel-, Art- und Satzfeld', async () => {
    const wrapper = mountDetail({ mode: 'create-relation' })
    const form = wrapper.get(`[data-testid="${GraphEditTestId.relationForm}"]`)
    const options = form.get(`[data-testid="${GraphEditTestId.relationSource}"]`).findAll('option')
    expect(options.map((o) => o.text())).toEqual(['—', 'Kreistag', 'Moorhagen', 'Neues Buero'])

    await form.get(`[data-testid="${GraphEditTestId.relationSource}"]`).setValue(EXTRACTED_NODE)
    await form.get(`[data-testid="${GraphEditTestId.relationTarget}"]`).setValue(MANUAL_NODE)
    await form.get(`[data-testid="${GraphEditTestId.relationName}"]`).setValue('ARBEITET_IN')
    await form.get(`[data-testid="${GraphEditTestId.relationFact}"]`).setValue('Sitzt dort.')
    await form.trigger('submit')

    expect(wrapper.emitted('create-relation')).toEqual([
      [{ source_uuid: EXTRACTED_NODE, target_uuid: MANUAL_NODE, name: 'ARBEITET_IN', fact: 'Sitzt dort.' }],
    ])
  })

  it('verlangt für eine Beziehung zwei verschiedene Enden', async () => {
    const wrapper = mountDetail({ mode: 'create-relation' })
    const source = wrapper.get(`[data-testid="${GraphEditTestId.relationSource}"]`)
    const target = wrapper.get(`[data-testid="${GraphEditTestId.relationTarget}"]`)
    await source.setValue(EXTRACTED_NODE)
    await target.setValue(EXTRACTED_NODE)
    await wrapper.get(`[data-testid="${GraphEditTestId.relationName}"]`).setValue('KENNT')
    await wrapper.get(`[data-testid="${GraphEditTestId.relationFact}"]`).setValue('x')
    expect(wrapper.get(`[data-testid="${GraphEditTestId.relationSubmit}"]`).attributes('disabled')).toBeDefined()

    await target.setValue(MANUAL_NODE)
    expect(wrapper.get(`[data-testid="${GraphEditTestId.relationSubmit}"]`).attributes('disabled')).toBeUndefined()
  })

  it('bearbeitet die gewählte Beziehung mit Art und Satz und markiert sie als bearbeitet', async () => {
    const wrapper = mountDetail({ relation: findRelation(EDITED_EDGE) })
    expect(wrapper.get(`[data-testid="${GraphEditTestId.markEdited}"]`).text()).toContain('bearbeitet')

    await wrapper.get(`[data-testid="${GraphEditTestId.relationFact}"]`).setValue('Neuer Satz.')
    await wrapper.get(`[data-testid="${GraphEditTestId.relationForm}"]`).trigger('submit')

    expect(wrapper.emitted('update-relation')).toEqual([[EDITED_EDGE, { fact: 'Neuer Satz.' }]])
  })

  it('fragt vor dem Löschen einer Beziehung nach', async () => {
    const wrapper = mountDetail({ relation: findRelation(EDITED_EDGE) })
    await wrapper.get(`[data-testid="${GraphEditTestId.relationDelete}"]`).trigger('click')
    expect(wrapper.emitted('delete-relation')).toBeUndefined()
    await wrapper.get(`[data-testid="${GraphEditTestId.relationDeleteConfirm}"]`).trigger('click')
    expect(wrapper.emitted('delete-relation')).toEqual([[EDITED_EDGE]])
  })

  it('führt Entitäten zusammen und nennt das Ziel sowie die Quellen', async () => {
    const wrapper = mountDetail({ entity: findEntity(EXTRACTED_NODE), mode: 'merge' })
    expect(wrapper.get(`[data-testid="${GraphEditTestId.mergePanel}"]`).text()).toContain('Kreistag')
    const submit = wrapper.get(`[data-testid="${GraphEditTestId.mergeSubmit}"]`)
    expect(submit.attributes('disabled')).toBeDefined()

    await wrapper.findAll(`[data-testid="${GraphEditTestId.mergeSource}"]`)[0]!.setValue(true)
    expect(wrapper.get(`[data-testid="${GraphEditTestId.mergeSubmit}"]`).attributes('disabled')).toBeUndefined()

    await submit.trigger('click')
    const arg = wrapper.emitted('merge')![0] as [unknown]
    // Der erste Kandidat der Liste ist Moorhagen — die Auswahl kommt aus der
    // Liste, nicht aus der Reihenfolge der Anlage.
    expect(arg[0]).toEqual({ target_uuid: EXTRACTED_NODE, source_uuids: [SECOND_NODE] })
  })

  it('bietet im gesperrten Zustand nur Lesen an, ohne Schaltflächen zum Schreiben', () => {
    const wrapper = mountDetail({ entity: findEntity(EXTRACTED_NODE), editable: false })
    expect(wrapper.find(`[data-testid="${GraphEditTestId.entityForm}"]`).exists()).toBe(false)
    expect(wrapper.find(`[data-testid="${GraphEditTestId.entityDelete}"]`).exists()).toBe(false)
    expect(wrapper.text()).toContain('nicht bearbeitbar')
  })

  it('nennt die Typen des Graphen als Auswahl, damit von Hand keine neuen entstehen', () => {
    const wrapper = mountDetail({ mode: 'create-entity' })
    const options = wrapper.get(`[data-testid="${GraphEditTestId.entityType}"]`).findAll('option')
    expect(options.map((o) => o.text())).toEqual(['—', 'Organisation', 'Ort'])
  })
})
