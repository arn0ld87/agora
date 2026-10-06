import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import GraphReader from '../GraphReader.vue'
import { buildReaderModel } from '@/composables/graph-library/graphReaderModel'
import { CanvasStub, focusSpy, graphFixture, makeI18n, makeRouter } from './fixtures'

vi.mock('@/api/graph', () => ({ exportGraphMl: vi.fn() }))

async function mountReader(query: Record<string, string> = {}): Promise<VueWrapper> {
  const router = makeRouter()
  await router.push({ path: '/graphs/proj_1', query })
  await router.isReady()
  const data = graphFixture()
  const wrapper = mount(GraphReader, {
    props: { model: buildReaderModel(data), graphData: data },
    global: { plugins: [makeI18n(), router], stubs: { GraphCanvas: CanvasStub } },
  })
  await flushPromises()
  return wrapper
}

function listNames(wrapper: VueWrapper): string[] {
  return wrapper.findAll('.gr__item .gr__itemname').map((n) => n.text())
}

beforeEach(() => focusSpy.mockClear())

describe('GraphReader', () => {
  it('zeigt Zahlen im Kopf, Typen mit Zählern und alle Entitäten', async () => {
    const wrapper = await mountReader()
    expect(wrapper.get('[data-testid="gr-counts"]').text()).toBe('4 Entitäten · 3 Beziehungen')
    const person = wrapper.get('[data-type="Person"]')
    expect(person.text()).toContain('2')
    expect(listNames(wrapper)).toHaveLength(4)
  })

  it('Typfilter und Suche grenzen die Liste ein, der Typfilter auch das Netz', async () => {
    const wrapper = await mountReader()
    await wrapper.get('[data-type="Person"]').trigger('click')
    expect(wrapper.get('[data-type="Person"]').attributes('aria-pressed')).toBe('true')
    expect(listNames(wrapper).sort()).toEqual(['Anna Berg', 'Bernd Voss'])
    expect(wrapper.get('[data-testid="canvas-stub"]').attributes('data-nodes')).toBe('2')

    await wrapper.get('input[type="search"]').setValue('voss')
    expect(listNames(wrapper)).toEqual(['Bernd Voss'])
    expect(wrapper.get('[data-testid="gr-list-count"]').text()).toBe('1')
  })

  it('findet Entitäten auch über Aliase', async () => {
    const wrapper = await mountReader()
    await wrapper.get('input[type="search"]').setValue('kreisrat')
    expect(listNames(wrapper)).toEqual(['Kreistag'])
  })

  it('meldet eine leere Trefferliste sichtbar', async () => {
    const wrapper = await mountReader()
    await wrapper.get('input[type="search"]').setValue('gibtsnicht')
    expect(wrapper.find('.gr__list').exists()).toBe(false)
    expect(wrapper.text()).toContain('Keine Entität passt zu Suche und Filter.')
  })

  it('schaltet zwischen Netz und Tabelle um', async () => {
    const wrapper = await mountReader()
    expect(wrapper.find('[data-testid="gr-net"]').exists()).toBe(true)
    expect(wrapper.find('table').exists()).toBe(false)

    await wrapper.get('[data-view="table"]').trigger('click')
    expect(wrapper.find('[data-testid="gr-net"]').exists()).toBe(false)
    expect(wrapper.get('[data-view="table"]').attributes('aria-pressed')).toBe('true')

    const table = wrapper.get('table')
    const heads = table.findAll('thead th')
    expect(heads.map((h) => h.attributes('scope'))).toEqual(['col', 'col', 'col', 'col'])
    expect(table.findAll('tbody th').every((h) => h.attributes('scope') === 'row')).toBe(true)

    await wrapper.get('[data-view="net"]').trigger('click')
    expect(wrapper.find('[data-testid="gr-net"]').exists()).toBe(true)
  })

  it('sortiert die Tabelle und setzt aria-sort', async () => {
    const wrapper = await mountReader()
    await wrapper.get('[data-view="table"]').trigger('click')
    const names = () => wrapper.findAll('tbody th button').map((b) => b.text().replace('›', '').trim())
    expect(names()).toEqual(['Anna Berg', 'Bernd Voss', 'Kreistag', 'Moorhagen'])
    expect(wrapper.findAll('thead th')[0].attributes('aria-sort')).toBe('ascending')

    await wrapper.findAll('thead th button')[0].trigger('click')
    expect(names()).toEqual(['Moorhagen', 'Kreistag', 'Bernd Voss', 'Anna Berg'])
    expect(wrapper.findAll('thead th')[0].attributes('aria-sort')).toBe('descending')

    // Zahlenspalte „Beziehungen“ numerisch, bei Gleichstand bleibt die Quellreihenfolge.
    await wrapper.findAll('thead th button')[2].trigger('click')
    expect(wrapper.findAll('thead th')[2].attributes('aria-sort')).toBe('ascending')
    expect(names()).toEqual(['Kreistag', 'Bernd Voss', 'Moorhagen', 'Anna Berg'])
    await wrapper.findAll('thead th button')[2].trigger('click')
    expect(wrapper.findAll('thead th')[2].attributes('aria-sort')).toBe('descending')
    expect(names()).toEqual(['Moorhagen', 'Anna Berg', 'Kreistag', 'Bernd Voss'])
  })

  it('zeigt Beziehungen als zweiten Reiter und wählt per Taste erreichbare Zeile', async () => {
    const wrapper = await mountReader()
    await wrapper.get('[data-view="table"]').trigger('click')
    await wrapper.get('#grt-tab-relations').trigger('click')
    expect(wrapper.get('#grt-tab-relations').attributes('aria-selected')).toBe('true')
    expect(wrapper.findAll('tbody tr')).toHaveLength(3)

    await wrapper.get('tr[data-edge-id="e1"] button').trigger('click')
    expect(wrapper.get('tr[data-edge-id="e1"] button').attributes('aria-current')).toBe('true')
    const detail = wrapper.get('aside')
    expect(detail.text()).toContain('Der Kreistag entscheidet über Moorhagen.')
    expect(detail.text()).toContain('Belegt durch 2 Quellenfragmente')
  })

  it('wählt per ?entity= aus, zeigt Details und zentriert im Netz', async () => {
    const wrapper = await mountReader({ entity: 'n1' })
    const detail = wrapper.get('aside')
    expect(detail.get('h2').text()).toBe('Kreistag')
    expect(detail.text()).toContain('Kreisrat')
    expect(detail.text()).toContain('Beschlussgremium des Landkreises')
    expect(detail.text()).toContain('sitz')
    expect(detail.text()).toContain('Beziehungen (1)')
    expect(detail.text()).toContain('Dokument und Abschnitt sind in den Graphdaten nicht hinterlegt.')
    expect(wrapper.get('[data-entity-id="n1"]').attributes('aria-current')).toBe('true')
    expect(focusSpy).toHaveBeenCalledWith({ nodeId: 'n1' })
  })

  it('akzeptiert für ?entity= auch den Namen', async () => {
    const wrapper = await mountReader({ entity: 'anna berg' })
    expect(wrapper.get('aside h2').text()).toBe('Anna Berg')
  })

  it('wählt per ?edge= die Beziehung und zentriert ihre Mitte', async () => {
    const wrapper = await mountReader({ edge: 'e2' })
    expect(wrapper.get('aside h2').text()).toBe('ARBEITET_IN')
    expect(focusSpy).toHaveBeenCalledWith({ edgeSource: 'n3', edgeTarget: 'n2' })
  })

  it('meldet ein unbekanntes Ziel sichtbar statt still zu ignorieren', async () => {
    const wrapper = await mountReader({ entity: 'gibtsnicht' })
    expect(wrapper.find('[data-testid="gr-target-missing"]').exists()).toBe(true)
  })

  it('übernimmt eine Auswahl im Netz in die Detailspalte', async () => {
    const wrapper = await mountReader()
    wrapper.getComponent(CanvasStub).vm.$emit('select', { type: 'node', data: { uuid: 'n3' } })
    await flushPromises()
    expect(wrapper.get('aside h2').text()).toBe('Anna Berg')
    expect(focusSpy).not.toHaveBeenCalled()
  })

  it('bietet weder Bearbeiten noch Löschen noch Zusammenführen an', async () => {
    const wrapper = await mountReader({ entity: 'n1' })
    const labels = wrapper.findAll('button').map((b) => b.text())
    expect(labels.some((l) => /löschen|zusammenführen|duplizieren|bearbeiten/i.test(l))).toBe(false)
  })
})
