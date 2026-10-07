/**
 * Bibliothek → Personasätze (#1807, Etappe 7): Kacheln, Suche, Anlegen-Dialog,
 * Duplizieren, Löschen mit Rückfrage (auch gesperrt), Lade-/Leer-/Fehlerzustand,
 * Zahl für die Seitenleiste.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { makeTestRouter } from '@/components/v4/shell/__tests__/testRouter'
import { PersonaSetLockedError } from '@/api/personaSets'
import { PERSONA_SET_NAME_MAX_LENGTH } from '@/contracts/personaSetContract'
import { PersonaSetTestId } from '@/contracts/testIds'
import { PersonaSetLibraryTestId as Id } from '@/components/persona-sets/library/libraryTestIds'
import { useShellStore } from '@/stores/shell'

const api = vi.hoisted(() => ({
  listPersonaSets: vi.fn(),
  createPersonaSet: vi.fn(),
  duplicatePersonaSet: vi.fn(),
  deletePersonaSet: vi.fn(),
}))

vi.mock('@/api/personaSets', async () => {
  const actual = await vi.importActual<typeof import('@/api/personaSets')>('@/api/personaSets')
  return { ...actual, ...api }
})

import LibraryPersonaSetsView from '../LibraryPersonaSetsView.vue'

vi.setConfig({ testTimeout: 20_000 })

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'de', messages: { de, en } })
const TS = '2026-10-07T10:00:00'

function summary(id: string, over: Record<string, unknown> = {}) {
  return {
    id, name: `Satz ${id}`, description: '', graph_id: null, project_id: null, entry_count: 4,
    locked: false, locked_at: null, usage_count: 0, created_at: TS, updated_at: TS, schema_version: 1 as const,
    ...over,
  }
}

function recordFor(id: string, name: string) {
  return {
    id, name, description: '', graph_id: null, project_id: null, entries: [], locked_at: null,
    used_by_simulation_ids: [], created_at: TS, updated_at: TS, schema_version: 1 as const,
  }
}

const LIST = [
  summary('a', { name: 'Gewerkschaften', description: 'Beschäftigte und Betriebsräte', entry_count: 1 }),
  summary('b', { name: 'Verbände', locked: true, locked_at: TS, usage_count: 2 }),
  summary('pset_importiert', { name: 'Importiert', usage_count: 1 }),
]

function listWith(sets: ReturnType<typeof summary>[]) {
  api.listPersonaSets.mockResolvedValue({ count: sets.length, sets })
}

async function mountView(): Promise<{ wrapper: VueWrapper; router: ReturnType<typeof makeTestRouter> }> {
  const router = makeTestRouter()
  await router.push('/library/persona-sets')
  await router.isReady()
  const wrapper = mount(LibraryPersonaSetsView, { global: { plugins: [router, i18n] }, attachTo: document.body })
  await flushPromises()
  return { wrapper, router }
}

const tile = (w: VueWrapper, id: string) => w.find(`[data-set-id="${id}"]`)

beforeEach(() => {
  setActivePinia(createPinia())
  for (const f of Object.values(api)) f.mockReset()
  document.body.innerHTML = ''
  listWith(LIST)
})

describe('LibraryPersonaSetsView — Kacheln', () => {
  it('zeigt je Satz Name, Beschreibung, Anzahl, Zustand, Verwendung und Datum', async () => {
    const { wrapper } = await mountView()
    expect(wrapper.findAll(`[data-testid="${Id.tile}"]`)).toHaveLength(3)
    const a = tile(wrapper, 'a')
    expect(a.find('h3').text()).toBe('Gewerkschaften')
    expect(a.text()).toContain('Beschäftigte und Betriebsräte')
    expect(a.text()).toContain('1 Persona')
    expect(a.text()).toContain('Bearbeitbar')
    expect(a.text()).toContain('Noch in keinem Lauf verwendet')
    expect(a.text()).toContain('07.10.2026')
    const b = tile(wrapper, 'b')
    expect(b.text()).toContain('4 Personas')
    expect(b.text()).toContain('Gesperrt')
    expect(b.text()).toContain('In 2 Läufen verwendet')
    expect(tile(wrapper, 'pset_importiert').text()).toContain('In 1 Lauf verwendet')
  })

  it('der Name öffnet den Satz (PersonaSet mit setId)', async () => {
    const { wrapper, router } = await mountView()
    await tile(wrapper, 'a').find(`[data-testid="${Id.tileOpen}"]`).trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('PersonaSet')
    expect(router.currentRoute.value.params.setId).toBe('a')
  })

  it('der Sammelsatz „Importiert“ erscheint wie jeder andere und trägt einen Hinweis', async () => {
    const { wrapper } = await mountView()
    const imported = tile(wrapper, 'pset_importiert')
    expect(imported.exists()).toBe(true)
    expect(imported.find(`[data-testid="${Id.importedNote}"]`).text()).toContain('pset_importiert')
    expect(tile(wrapper, 'a').find(`[data-testid="${Id.importedNote}"]`).exists()).toBe(false)
  })

  it('Knöpfe sind beschriftet und erreichbar; der Löschknopf eines gesperrten Satzes ist deaktiviert mit Begründung', async () => {
    const { wrapper } = await mountView()
    const del = tile(wrapper, 'b').find(`[data-testid="${Id.tileDelete}"]`)
    expect(del.attributes('disabled')).toBeDefined()
    const reasonId = del.attributes('aria-describedby')
    expect(reasonId).toBeTruthy()
    expect(wrapper.find(`#${reasonId}`).text()).toContain('nicht löschen')
    expect(tile(wrapper, 'a').find(`[data-testid="${Id.tileDelete}"]`).attributes('disabled')).toBeUndefined()
    expect(tile(wrapper, 'a').find('[role="group"]').attributes('aria-label')).toContain('Gewerkschaften')
  })

  it('Suche filtert nach Namen und meldet Treffer bzw. keine Treffer', async () => {
    const { wrapper } = await mountView()
    const search = wrapper.find(`[data-testid="${Id.search}"]`)
    expect(search.attributes('aria-label')).toBeTruthy()
    await search.setValue('verb')
    expect(wrapper.findAll(`[data-testid="${Id.tile}"]`).map((t) => t.attributes('data-set-id'))).toEqual(['b'])
    expect(wrapper.find(`[data-testid="${Id.status}"]`).text()).toContain('1 von 3')
    await search.setValue('zzz')
    expect(wrapper.find(`[data-testid="${Id.noMatches}"]`).text()).toContain('zzz')
    expect(wrapper.findAll(`[data-testid="${Id.tile}"]`)).toHaveLength(0)
  })
})

describe('LibraryPersonaSetsView — Zustände', () => {
  it('zeigt beim Laden einen Status', async () => {
    api.listPersonaSets.mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountView()
    const loading = wrapper.find(`[data-testid="${PersonaSetTestId.loading}"]`)
    expect(loading.attributes('role')).toBe('status')
    expect(loading.attributes('aria-busy')).toBe('true')
  })

  it('Leerzustand mit Aufruf zum Anlegen', async () => {
    listWith([])
    const { wrapper } = await mountView()
    expect(wrapper.find(`[data-testid="${PersonaSetTestId.empty}"]`).exists()).toBe(true)
    await wrapper.find(`[data-testid="${Id.emptyNew}"]`).trigger('click')
    await flushPromises()
    expect(document.querySelector('[role="dialog"]')).not.toBeNull()
  })

  it('Fehler mit „Erneut versuchen“, danach erscheinen die Kacheln', async () => {
    api.listPersonaSets.mockRejectedValueOnce(new Error('Server nicht erreichbar'))
    const { wrapper } = await mountView()
    const err = wrapper.find(`[data-testid="${PersonaSetTestId.error}"]`)
    expect(err.attributes('role')).toBe('alert')
    expect(err.text()).toContain('Server nicht erreichbar')
    expect(useShellStore().personaSetCount).toBeNull()
    expect(useShellStore().personaSetCountFailed).toBe(true)
    await err.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.findAll(`[data-testid="${Id.tile}"]`)).toHaveLength(3)
    expect(useShellStore().personaSetCountFailed).toBe(false)
  })

  it('veröffentlicht die Zahl der Sätze für die Seitenleiste', async () => {
    await mountView()
    expect(useShellStore().personaSetCount).toBe(3)
  })
})

describe('LibraryPersonaSetsView — Anlegen', () => {
  async function openDialog(wrapper: VueWrapper) {
    await wrapper.find(`[data-testid="${Id.newButton}"]`).trigger('click')
    await flushPromises()
    return document.body
  }

  it('Dialog ist modal, beschriftet und der Fokus wandert hinein; Abbrechen gibt den Fokus zurück', async () => {
    const { wrapper } = await mountView()
    const trigger = wrapper.find(`[data-testid="${Id.newButton}"]`).element as HTMLElement
    trigger.focus()
    const body = await openDialog(wrapper)
    const dialog = body.querySelector('[role="dialog"]') as HTMLElement
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(dialog.getAttribute('aria-labelledby')).toBe('dlg-title')
    expect(dialog.contains(document.activeElement)).toBe(true)
    ;(body.querySelector(`[data-testid="${Id.createCancel}"]`) as HTMLElement).click()
    await flushPromises()
    expect(body.querySelector('[role="dialog"]')).toBeNull()
    expect(document.activeElement).toBe(trigger)
  })

  it('Name ist Pflicht: leer sendet nichts und zeigt den Fehler', async () => {
    const { wrapper } = await mountView()
    const body = await openDialog(wrapper)
    ;(body.querySelector(`[data-testid="${Id.createSubmit}"]`) as HTMLElement).click()
    await flushPromises()
    expect(api.createPersonaSet).not.toHaveBeenCalled()
    expect(body.querySelector(`[data-testid="${Id.createNameError}"]`)?.textContent).toContain('Namen')
    expect(body.querySelector(`[data-testid="${Id.createName}"]`)?.getAttribute('aria-invalid')).toBe('true')
  })

  it('zu langer Name sendet nichts', async () => {
    const { wrapper } = await mountView()
    const body = await openDialog(wrapper)
    const input = body.querySelector(`[data-testid="${Id.createName}"]`) as HTMLInputElement
    input.value = 'x'.repeat(PERSONA_SET_NAME_MAX_LENGTH + 1)
    input.dispatchEvent(new Event('input'))
    ;(body.querySelector(`[data-testid="${Id.createSubmit}"]`) as HTMLElement).click()
    await flushPromises()
    expect(api.createPersonaSet).not.toHaveBeenCalled()
    expect(body.querySelector(`[data-testid="${Id.createNameError}"]`)?.textContent).toContain(String(PERSONA_SET_NAME_MAX_LENGTH))
  })

  it('legt an (Name getrimmt) und öffnet den neuen Satz', async () => {
    api.createPersonaSet.mockResolvedValue(recordFor('neu', 'Neuer Satz'))
    const { wrapper, router } = await mountView()
    const body = await openDialog(wrapper)
    const input = body.querySelector(`[data-testid="${Id.createName}"]`) as HTMLInputElement
    input.value = '  Neuer Satz  '
    input.dispatchEvent(new Event('input'))
    const area = body.querySelector(`[data-testid="${Id.createDescription}"]`) as HTMLTextAreaElement
    area.value = 'Beschreibung'
    area.dispatchEvent(new Event('input'))
    ;(body.querySelector(`[data-testid="${Id.createSubmit}"]`) as HTMLElement).click()
    await flushPromises()
    expect(api.createPersonaSet).toHaveBeenCalledWith({ name: 'Neuer Satz', description: 'Beschreibung' })
    expect(router.currentRoute.value.name).toBe('PersonaSet')
    expect(router.currentRoute.value.params.setId).toBe('neu')
    expect(body.querySelector('[role="dialog"]')).toBeNull()
  })

  it('Fehler beim Anlegen bleibt im offenen Dialog sichtbar', async () => {
    api.createPersonaSet.mockRejectedValue(new Error('Speichern fehlgeschlagen'))
    const { wrapper, router } = await mountView()
    const body = await openDialog(wrapper)
    const input = body.querySelector(`[data-testid="${Id.createName}"]`) as HTMLInputElement
    input.value = 'Satz'
    input.dispatchEvent(new Event('input'))
    ;(body.querySelector(`[data-testid="${Id.createSubmit}"]`) as HTMLElement).click()
    await flushPromises()
    expect(body.querySelector('[role="dialog"]')).not.toBeNull()
    expect(body.querySelector('[data-testid="persona-set-create-error"]')?.textContent).toContain('Speichern fehlgeschlagen')
    expect(router.currentRoute.value.name).toBe('LibraryPersonaSets')
  })
})

describe('LibraryPersonaSetsView — Duplizieren und Löschen', () => {
  it('Duplizieren legt „… (Kopie)“ an und öffnet den neuen Satz', async () => {
    api.duplicatePersonaSet.mockResolvedValue(recordFor('kopie', 'Gewerkschaften (Kopie)'))
    const { wrapper, router } = await mountView()
    await tile(wrapper, 'b').find(`[data-testid="${Id.tileDuplicate}"]`).trigger('click')
    await flushPromises()
    expect(api.duplicatePersonaSet).toHaveBeenCalledWith('b', { name: 'Verbände (Kopie)' })
    expect(router.currentRoute.value.name).toBe('PersonaSet')
    expect(router.currentRoute.value.params.setId).toBe('kopie')
  })

  it('Löschen fragt zuerst nach; Abbrechen löscht nichts', async () => {
    const { wrapper } = await mountView()
    await tile(wrapper, 'a').find(`[data-testid="${Id.tileDelete}"]`).trigger('click')
    await flushPromises()
    const dialog = document.body.querySelector('[role="dialog"]') as HTMLElement
    expect(dialog.textContent).toContain('Gewerkschaften')
    expect(api.deletePersonaSet).not.toHaveBeenCalled()
    ;(document.body.querySelector(`[data-testid="${Id.removeCancel}"]`) as HTMLElement).click()
    await flushPromises()
    expect(api.deletePersonaSet).not.toHaveBeenCalled()
    expect(document.body.querySelector('[role="dialog"]')).toBeNull()
  })

  it('bestätigtes Löschen ruft das Backend, lädt neu und meldet es in der Live-Region', async () => {
    api.deletePersonaSet.mockResolvedValue({ removed: 'a' })
    const { wrapper } = await mountView()
    await tile(wrapper, 'a').find(`[data-testid="${Id.tileDelete}"]`).trigger('click')
    await flushPromises()
    api.listPersonaSets.mockResolvedValue({ count: 2, sets: LIST.slice(1) })
    ;(document.body.querySelector(`[data-testid="${Id.removeConfirm}"]`) as HTMLElement).click()
    await flushPromises()
    expect(api.deletePersonaSet).toHaveBeenCalledWith('a')
    expect(tile(wrapper, 'a').exists()).toBe(false)
    expect(wrapper.find(`[data-testid="${Id.status}"]`).text()).toContain('gelöscht')
    expect(wrapper.find(`[data-testid="${Id.status}"]`).attributes('role')).toBe('status')
    expect(useShellStore().personaSetCount).toBe(2)
  })

  it('lehnt das Backend das Löschen als gesperrt ab (409), erscheint eine verständliche Meldung', async () => {
    api.deletePersonaSet.mockRejectedValue(new PersonaSetLockedError('persona_set_locked'))
    const { wrapper } = await mountView()
    await tile(wrapper, 'a').find(`[data-testid="${Id.tileDelete}"]`).trigger('click')
    await flushPromises()
    ;(document.body.querySelector(`[data-testid="${Id.removeConfirm}"]`) as HTMLElement).click()
    await flushPromises()
    const alert = wrapper.find(`[data-testid="${Id.actionError}"]`)
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('gesperrt')
    expect(alert.text()).toContain('duplizieren')
    expect(tile(wrapper, 'a').exists()).toBe(true)
  })
})
