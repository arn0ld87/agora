/**
 * Satz-Ansicht (#1807, E7-F2): Herkunftsmarken, Filter, Mehrfachlöschen mit
 * Rückfrage, Sperrzustand, Duplizieren, Qualitäts-Fehlerzustand, 404.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import { ApiError } from '@/api/envelope'
import { PersonaSetDetailTestId as Id } from '@/components/persona-sets/detailTestIds'
import { PersonaSetTestId } from '@/contracts/testIds'

const api = vi.hoisted(() => ({
  getPersonaSet: vi.fn(),
  getPersonaSetQuality: vi.fn(),
  deletePersonaSetEntries: vi.fn(),
  duplicatePersonaSet: vi.fn(),
  addPersonaSetEntry: vi.fn(),
  updatePersonaSetEntry: vi.fn(),
  updatePersonaSet: vi.fn(),
  deletePersonaSetEntry: vi.fn(),
}))
vi.mock('@/api/personaSets', async () => {
  const actual = await vi.importActual<typeof import('@/api/personaSets')>('@/api/personaSets')
  return { ...actual, ...api }
})

import PersonaSetView from '../PersonaSetView.vue'

vi.setConfig({ testTimeout: 20_000 })

const TS = '2026-10-07T10:00:00'
type Origin = 'graph' | 'manual' | 'ai_draft' | 'fallback'
function entry(id: string, origin: Origin, extra: Record<string, unknown> = {}) {
  return {
    entry_id: id, origin, source_entity_uuid: null, created_at: TS, updated_at: TS,
    profile: {
      username: `u_${id}`, name: `Person ${id}`, bio: '', persona: '', age: null, gender: null, mbti: null,
      country: null, profession: 'Pflegekraft', interested_topics: [], source_entity_type: null,
      persona_kind: 'individual', language: null, activity_level: null, time_zone: null, location: null,
      verified: false, ...extra,
    },
  }
}
function setRecord(locked = false) {
  return {
    id: 's1', name: 'Satz Eins', description: 'Beschreibung', graph_id: null, project_id: null,
    entries: [
      entry('a', 'graph'),
      entry('b', 'manual', { profession: 'Arzt', persona_kind: 'collective' }),
      entry('c', 'ai_draft'),
      entry('d', 'fallback'),
    ],
    locked_at: locked ? TS : null,
    used_by_simulation_ids: locked ? ['sim_1'] : [],
    created_at: TS, updated_at: TS, schema_version: 1 as const,
  }
}
const quality = {
  set_id: 's1',
  summary: { total: 4, role_diversity: 0.5, mbti_diversity: 0, distinct_roles: ['Arzt'], distinct_mbti: [] },
  global_issues: [],
  personas: [{ entry_id: 'a', username: 'u_a', issues: [{ code: 'missing_mbti', severity: 'warning' }] }],
}

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'de', messages: { de } })
const stub = { template: '<div/>' }

async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/persona-sets/:setId', name: 'PersonaSet', component: stub },
      { path: '/library/persona-sets', name: 'LibraryPersonaSets', component: stub },
      { path: '/simulation/:simulationId', name: 'Simulation', component: stub },
    ],
  })
  await router.push('/persona-sets/s1')
  await router.isReady()
  const wrapper = mount(PersonaSetView, { props: { setId: 's1' }, global: { plugins: [i18n, router] }, attachTo: document.body })
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => {
  for (const f of Object.values(api)) f.mockReset()
  api.getPersonaSet.mockResolvedValue(setRecord())
  api.getPersonaSetQuality.mockResolvedValue(quality)
  document.body.innerHTML = ''
})

describe('PersonaSetView', () => {
  it('zeigt Karten mit Herkunftsmarke; fallback und ai_draft tragen Text und Hinweis', async () => {
    const { wrapper } = await mountView()
    const cards = wrapper.findAll(`[data-testid="${Id.card}"]`)
    expect(cards).toHaveLength(4)
    const text = (origin: string) => wrapper.find(`[data-origin="${origin}"]`).text()
    expect(text('graph')).toContain('aus Graph')
    expect(text('manual')).toContain('von Hand')
    expect(text('ai_draft')).toContain('KI-Entwurf')
    expect(text('ai_draft')).toContain('Entwurf')
    expect(text('fallback')).toContain('Fallback')
    expect(text('fallback')).toContain('Degradation')
    wrapper.unmount()
  })

  it('filtert nach Herkunft, Art und Suche und zählt „x von y“', async () => {
    const { wrapper } = await mountView()
    expect(wrapper.get(`[data-testid="${Id.filterCount}"]`).text()).toBe('4 von 4')
    await wrapper.get(`[data-testid="${Id.filterOrigin}"]`).setValue('fallback')
    expect(wrapper.findAll(`[data-testid="${Id.card}"]`)).toHaveLength(1)
    expect(wrapper.get(`[data-testid="${Id.filterCount}"]`).text()).toBe('1 von 4')
    await wrapper.get(`[data-testid="${Id.filterReset}"]`).trigger('click')
    await wrapper.get(`[data-testid="${Id.filterKind}"]`).setValue('collective')
    expect(wrapper.findAll(`[data-testid="${Id.card}"]`)).toHaveLength(1)
    await wrapper.get(`[data-testid="${Id.filterReset}"]`).trigger('click')
    await wrapper.get(`[data-testid="${Id.filterSearch}"]`).setValue('person c')
    expect(wrapper.findAll(`[data-testid="${Id.card}"]`)).toHaveLength(1)
    await wrapper.get(`[data-testid="${Id.filterSearch}"]`).setValue('gibtesnicht')
    expect(wrapper.find(`[data-testid="${Id.noMatches}"]`).exists()).toBe(true)
    wrapper.unmount()
  })

  it('löscht Mehrfachauswahl erst nach Rückfrage', async () => {
    api.deletePersonaSetEntries.mockResolvedValue({ removed_entry_ids: ['a', 'b'], set: {} })
    const { wrapper } = await mountView()
    const boxes = wrapper.findAll(`[data-testid="${Id.cardSelect}"]`)
    await boxes[0].setValue(true)
    await boxes[1].setValue(true)
    await wrapper.get(`[data-testid="${Id.deleteSelected}"]`).trigger('click')
    expect(api.deletePersonaSetEntries).not.toHaveBeenCalled()
    expect(wrapper.find(`[data-testid="${Id.deleteConfirm}"]`).exists()).toBe(true)
    await wrapper.get(`[data-testid="${Id.deleteConfirmYes}"]`).trigger('click')
    await flushPromises()
    expect(api.deletePersonaSetEntries).toHaveBeenCalledWith('s1', ['a', 'b'])
    expect(wrapper.findAll(`[data-testid="${Id.card}"]`)).toHaveLength(2)
    wrapper.unmount()
  })

  it('Abbrechen der Rückfrage löscht nichts', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll(`[data-testid="${Id.cardSelect}"]`)[0].setValue(true)
    await wrapper.get(`[data-testid="${Id.deleteSelected}"]`).trigger('click')
    await wrapper.get(`[data-testid="${Id.deleteConfirmNo}"]`).trigger('click')
    expect(api.deletePersonaSetEntries).not.toHaveBeenCalled()
    expect(wrapper.find(`[data-testid="${Id.deleteConfirm}"]`).exists()).toBe(false)
    wrapper.unmount()
  })

  it('deaktiviert bei gesperrtem Satz alle ändernden Elemente und nennt den Grund', async () => {
    api.getPersonaSet.mockResolvedValue(setRecord(true))
    const { wrapper } = await mountView()
    expect(wrapper.find(`[data-testid="${PersonaSetTestId.locked}"]`).exists()).toBe(true)
    expect(wrapper.get(`[data-testid="${Id.state}"]`).text()).toContain('gesperrt')
    expect(wrapper.get(`[data-testid="${Id.add}"]`).attributes('disabled')).toBeDefined()
    expect(wrapper.get(`[data-testid="${Id.deleteSelected}"]`).attributes('disabled')).toBeDefined()
    expect(wrapper.get(`[data-testid="${Id.selectAll}"]`).attributes('disabled')).toBeDefined()
    for (const box of wrapper.findAll(`[data-testid="${Id.cardSelect}"]`)) {
      expect(box.attributes('disabled')).toBeDefined()
    }
    expect(wrapper.get(`[data-testid="${Id.lockedReason}"]`).text()).toContain('gesperrt')
    expect(wrapper.get(`[data-testid="${Id.add}"]`).attributes('aria-describedby')).toBe(Id.lockedReason)
    expect(wrapper.get(`[data-testid="${Id.usedBy}"]`).text()).toContain('sim_1')
    // Umbenennen bleibt erlaubt
    expect(wrapper.get(`[data-testid="${Id.rename}"]`).attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('Duplizieren führt auf den neuen Satz', async () => {
    api.duplicatePersonaSet.mockResolvedValue({ ...setRecord(), id: 's2' })
    const { wrapper, router } = await mountView()
    await wrapper.get(`[data-testid="${Id.duplicate}"]`).trigger('click')
    await flushPromises()
    expect(api.duplicatePersonaSet).toHaveBeenCalledWith('s1', { name: 'Satz Eins (Kopie)' })
    expect(router.currentRoute.value.params.setId).toBe('s2')
    wrapper.unmount()
  })

  it('zeigt Fehler beim Duplizieren', async () => {
    api.duplicatePersonaSet.mockRejectedValue(new Error('kaputt'))
    const { wrapper } = await mountView()
    await wrapper.get(`[data-testid="${Id.duplicate}"]`).trigger('click')
    await flushPromises()
    expect(wrapper.get(`[data-testid="${Id.duplicateError}"]`).text()).toContain('kaputt')
    wrapper.unmount()
  })

  it('zeigt Qualitätshinweise an der Karte und die Zusammenfassung', async () => {
    const { wrapper } = await mountView()
    expect(wrapper.get(`[data-testid="${Id.qualityBox}"]`).text()).toContain('4 Personas')
    expect(wrapper.get(`[data-testid="${Id.qualityHint}"]`).text()).toContain('missing_mbti')
    wrapper.unmount()
  })

  it('zeigt den Qualitäts-Fehlerzustand mit Erneut-Versuchen', async () => {
    api.getPersonaSetQuality.mockRejectedValueOnce(new Error('quality down'))
    const { wrapper } = await mountView()
    expect(wrapper.get(`[data-testid="${Id.qualityError}"]`).text()).toContain('quality down')
    await wrapper.get(`[data-testid="${Id.qualityRetry}"]`).trigger('click')
    await flushPromises()
    expect(wrapper.find(`[data-testid="${Id.qualityError}"]`).exists()).toBe(false)
    expect(api.getPersonaSetQuality).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('zeigt 404 als „nicht gefunden“', async () => {
    api.getPersonaSet.mockRejectedValue(new ApiError({ code: 'not_found', status: 404, message: 'nope' }))
    const { wrapper } = await mountView()
    expect(wrapper.get(`[data-testid="${Id.notFound}"]`).text()).toContain('nicht gefunden')
    wrapper.unmount()
  })

  it('zeigt Ladefehler mit Erneut-Versuchen und den leeren Satz', async () => {
    api.getPersonaSet.mockRejectedValueOnce(new Error('offline'))
    const { wrapper } = await mountView()
    expect(wrapper.get(`[data-testid="${PersonaSetTestId.error}"]`).text()).toContain('offline')
    api.getPersonaSet.mockResolvedValue({ ...setRecord(), entries: [] })
    await wrapper.get(`[data-testid="${Id.retry}"]`).trigger('click')
    await flushPromises()
    expect(wrapper.find(`[data-testid="${PersonaSetTestId.empty}"]`).exists()).toBe(true)
    wrapper.unmount()
  })

  it('Editor-Platzhalter legt eine Persona an und gibt den Fokus zurück', async () => {
    api.addPersonaSetEntry.mockResolvedValue(entry('n', 'manual', { name: 'Neu', username: 'neu' }))
    const { wrapper } = await mountView()
    const add = wrapper.get<HTMLButtonElement>(`[data-testid="${Id.add}"]`)
    add.element.focus()
    await add.trigger('click')
    await wrapper.get(`[data-testid="${Id.editorName}"]`).setValue('Neu')
    await wrapper.get(`[data-testid="${Id.editorUsername}"]`).setValue('neu')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(api.addPersonaSetEntry).toHaveBeenCalledTimes(1)
    const [setId, body] = api.addPersonaSetEntry.mock.calls[0]
    expect(setId).toBe('s1')
    expect(body.origin).toBe('manual')
    expect(body.profile.name).toBe('Neu')
    expect(wrapper.find(`[data-testid="${Id.editor}"]`).exists()).toBe(false)
    expect(document.activeElement).toBe(add.element)
    wrapper.unmount()
  })

  it('Klick auf eine Karte öffnet den Editor mit der Persona', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll(`[data-testid="${Id.cardOpen}"]`)[1].trigger('click')
    expect((wrapper.get(`[data-testid="${Id.editorName}"]`).element as HTMLInputElement).value).toBe('Person b')
    wrapper.unmount()
  })
})
