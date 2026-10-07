/**
 * Persona-Editor (#1807, E7-F3): Abschnitte, Validierung am Feld, schema-gültiges
 * `save`, Sperrzustand, Rückfrage bei ungespeicherten Änderungen, Herkunftsmarke.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import {
  PersonaSetProfileInputSchema,
  type PersonaOrigin,
  type PersonaSetEntry,
} from '@/contracts/personaSetContract'
import { PersonaSetDetailTestId as Id } from '../detailTestIds'
import PersonaEditorDialog from '../PersonaEditorDialog.vue'
import { FIELD_SECTION, PROFILE_LIMITS } from '../editor/editorModel'

const TS = '2026-10-07T10:00:00'
const FULL_PROFILE = {
  username: 'pflege_anna',
  name: 'Anna Beispiel',
  bio: 'Pflegefachkraft',
  persona: 'Ausführliche Beschreibung\nmit Zeilenumbruch.',
  age: 42,
  gender: 'female' as const,
  mbti: 'ISFJ' as const,
  country: 'DE',
  profession: 'Pflegekraft',
  interested_topics: ['Pflege', 'Tarifpolitik'],
  source_entity_type: 'Person',
  persona_kind: 'collective' as const,
  language: 'de',
  activity_level: 0.35,
  time_zone: 'Europe/Berlin',
  location: 'Leipzig',
  verified: true,
}

function entry(origin: PersonaOrigin = 'graph'): PersonaSetEntry {
  return {
    entry_id: 'e1', origin, source_entity_uuid: 'uuid-123', created_at: TS, updated_at: TS,
    profile: { ...FULL_PROFILE },
  }
}

const mounted: VueWrapper[] = []
function mountEditor(props: Record<string, unknown> = {}) {
  const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'de', messages: { de } })
  const wrapper = mount(PersonaEditorDialog, {
    props: { open: true, entry: null, locked: false, ...props },
    global: { plugins: [i18n] },
    attachTo: document.body,
  })
  mounted.push(wrapper)
  return wrapper
}
afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount()
})

const tid = (id: string) => `[data-testid="${id}"]`
const field = (w: VueWrapper, name: string) => w.get(`[id$="-${name}"]`)

describe('PersonaEditorDialog: Abschnitte', () => {
  it('zeigt fünf Abschnitte, Identität zuerst, Wechsel per Klick und Pfeiltasten', async () => {
    const w = mountEditor()
    const tabs = w.findAll(tid(Id.editorTab))
    expect(tabs.map((t) => t.text())).toEqual([
      'Identität', 'Haltung und Ziele', 'Sprache und Ton', 'Aktivität', 'Bezug zum Graphen',
    ])
    expect(w.get(tid(Id.editorPanel)).attributes('data-section')).toBe('identity')
    expect(tabs.map((t) => t.attributes('tabindex'))).toEqual(['0', '-1', '-1', '-1', '-1'])

    await tabs[3].trigger('click')
    expect(w.get(tid(Id.editorPanel)).attributes('data-section')).toBe('activity')
    expect(tabs[3].attributes('aria-selected')).toBe('true')

    await tabs[3].trigger('keydown', { key: 'ArrowDown' })
    expect(w.get(tid(Id.editorPanel)).attributes('data-section')).toBe('graph')
    await w.findAll(tid(Id.editorTab))[4].trigger('keydown', { key: 'ArrowDown' })
    expect(w.get(tid(Id.editorPanel)).attributes('data-section')).toBe('identity')
    await w.findAll(tid(Id.editorTab))[0].trigger('keydown', { key: 'End' })
    expect(w.get(tid(Id.editorPanel)).attributes('data-section')).toBe('graph')
  })

  it('weist Haltung und Sprache ehrlich auf fehlende Vertragsfelder hin', async () => {
    const w = mountEditor()
    await w.findAll(tid(Id.editorTab))[1].trigger('click')
    expect(w.text()).toContain('kein eigenes Feld für Haltung oder Ziele')
    await w.findAll(tid(Id.editorTab))[2].trigger('click')
    expect(w.text()).toContain('kein eigenes Feld für Ton oder Stil')
  })

  it('zeigt im Graph-Abschnitt Herkunft und Quell-Entität lesend', async () => {
    const w = mountEditor({ entry: entry('graph') })
    await w.findAll(tid(Id.editorTab))[4].trigger('click')
    expect(w.get(tid('persona-editor-graph-origin')).text()).toBe('aus Graph')
    expect(w.get(tid('persona-editor-graph-uuid')).text()).toBe('uuid-123')
    expect((field(w, 'source_entity_type').element as HTMLInputElement).value).toBe('Person')
  })

  it('hat keine KI-Knöpfe', () => {
    const w = mountEditor()
    const labels = w.findAll('button').map((b) => b.text())
    expect(labels.join('|')).not.toMatch(/Entwurf aus Stichworten|vorschlagen|Vorschau/)
  })
})

describe('PersonaEditorDialog: Validierung', () => {
  it('meldet Pflichtfelder am Feld und oben, Fokus springt zum ersten Fehler', async () => {
    const w = mountEditor()
    await w.get('form').trigger('submit')
    expect(w.emitted('save')).toBeUndefined()
    const summary = w.get(tid(Id.editorSummary))
    expect(summary.attributes('role')).toBe('alert')
    expect(summary.findAll(tid(Id.editorSummaryItem))).toHaveLength(2)

    const name = field(w, 'name')
    expect(name.attributes('aria-invalid')).toBe('true')
    const errorId = name.attributes('aria-describedby')?.split(' ').pop() ?? ''
    expect(document.getElementById(errorId)?.textContent).toContain('Pflichtfeld')
    expect(document.activeElement).toBe(name.element)
  })

  it('wechselt zum Abschnitt des ersten Fehlers und prüft Wertgrenzen', async () => {
    const w = mountEditor({ entry: entry() })
    await w.findAll(tid(Id.editorTab))[3].trigger('click')
    await field(w, 'activity_level').setValue('2')
    await w.findAll(tid(Id.editorTab))[0].trigger('click')
    await field(w, 'age').setValue('abc')
    await field(w, 'country').setValue('DEU')
    await w.get('form').trigger('submit')

    expect(w.emitted('save')).toBeUndefined()
    expect(w.get(tid(Id.editorPanel)).attributes('data-section')).toBe('identity')
    expect(document.activeElement).toBe(field(w, 'age').element)
    expect(w.text()).toContain('Ganze Zahl angeben.')
    expect(w.text()).toContain('Zweibuchstabiger Ländercode')
    // Fehler im Abschnitt Aktivität steht in der Navigation und in der Zusammenfassung.
    expect(w.findAll(tid(Id.editorTab))[3].text()).toContain('1')
    expect(w.get(tid(Id.editorSummary)).text()).toContain('Wert zwischen 0 und 1')
  })

  it('meldet Überlänge mit der Grenze aus dem Vertrag', async () => {
    const w = mountEditor()
    await field(w, 'name').setValue('Name')
    await field(w, 'username').setValue('x'.repeat(PROFILE_LIMITS.username + 1))
    await w.get('form').trigger('submit')
    expect(w.text()).toContain(`höchstens ${PROFILE_LIMITS.username} Zeichen`)
    expect(w.emitted('save')).toBeUndefined()
  })

  it('markiert Pflichtfelder mit Stern und Screenreader-Text', () => {
    const w = mountEditor()
    const label = w.get('label[for$="-name"]')
    expect(label.text()).toContain('*')
    expect(label.text()).toContain('Pflichtfeld')
    expect(field(w, 'name').attributes('aria-required')).toBe('true')
  })
})

describe('PersonaEditorDialog: Speichern', () => {
  it('emittiert eine schema-gültige Eingabe für eine neue Persona', async () => {
    const w = mountEditor()
    await field(w, 'name').setValue('  Neu  ')
    await field(w, 'username').setValue('neu')
    await w.get('form').trigger('submit')
    const [payload] = w.emitted('save')![0] as [unknown]
    expect(PersonaSetProfileInputSchema.safeParse(payload).success).toBe(true)
    expect(payload).toMatchObject({ name: 'Neu', username: 'neu', age: null, persona_kind: 'individual', interested_topics: [] })
  })

  it('gibt bei einer vorhandenen Persona alle Felder unverändert zurück', async () => {
    const w = mountEditor({ entry: entry('ai_draft') })
    await w.get('form').trigger('submit')
    const [payload] = w.emitted('save')![0] as [unknown]
    expect(PersonaSetProfileInputSchema.safeParse(payload).success).toBe(true)
    expect(payload).toEqual(FULL_PROFILE)
    expect(payload).not.toHaveProperty('origin')
  })

  it('übernimmt Änderungen aus mehreren Abschnitten', async () => {
    const w = mountEditor({ entry: entry() })
    await field(w, 'age').setValue('')
    await field(w, 'gender').setValue('')
    await w.findAll(tid(Id.editorTab))[1].trigger('click')
    await field(w, 'interested_topics').setValue('A\n\n B \n')
    await w.findAll(tid(Id.editorTab))[3].trigger('click')
    await field(w, 'activity_level').setValue('0,5')
    await w.get('form').trigger('submit')
    const [payload] = w.emitted('save')![0] as [Record<string, unknown>]
    expect(payload).toMatchObject({ age: null, gender: null, interested_topics: ['A', 'B'], activity_level: 0.5 })
  })

  it('zeigt busy und error sichtbar', () => {
    const w = mountEditor({ busy: true, error: 'Konflikt: Benutzername' })
    expect(w.get(tid(Id.editorSave)).attributes('disabled')).toBeDefined()
    expect(w.get(tid(Id.editorSave)).text()).toContain('Wird gespeichert')
    expect(w.get(tid(Id.editorLive)).text()).toContain('Wird gespeichert')
    expect(w.get(tid(Id.editorError)).text()).toContain('Konflikt: Benutzername')
  })
})

describe('PersonaEditorDialog: Sperrzustand', () => {
  it('macht alles lesbar, nennt den Grund und speichert nicht', async () => {
    const w = mountEditor({ entry: entry(), locked: true })
    expect(w.get(tid(Id.editorLockedReason)).text()).toContain('Gesperrt')
    expect((field(w, 'name').element as HTMLInputElement).readOnly).toBe(true)
    expect((field(w, 'gender').element as HTMLSelectElement).disabled).toBe(true)
    expect(w.get(tid(Id.editorSave)).attributes('disabled')).toBeDefined()
    await w.get('form').trigger('submit')
    expect(w.emitted('save')).toBeUndefined()
    await w.get(tid(Id.editorCancel)).trigger('click')
    expect(w.emitted('update:open')).toEqual([[false]])
  })
})

describe('PersonaEditorDialog: ungespeicherte Änderungen', () => {
  it('schließt ohne Änderung direkt', async () => {
    const w = mountEditor({ entry: entry() })
    await w.get(tid(Id.editorCancel)).trigger('click')
    expect(w.emitted('update:open')).toEqual([[false]])
    expect(w.find(tid(Id.editorConfirm)).exists()).toBe(false)
  })

  it('fragt bei Änderungen nach; Weiterbearbeiten behält den Entwurf, Verwerfen schließt', async () => {
    const w = mountEditor({ entry: entry() })
    await field(w, 'name').setValue('Geändert')
    expect(w.text()).toContain('Ungespeicherte Änderungen')
    await w.get(tid(Id.editorCancel)).trigger('click')
    expect(w.emitted('update:open')).toBeUndefined()
    expect(w.get(tid(Id.editorConfirm)).attributes('role')).toBe('alert')
    expect(document.activeElement).toBe(w.get(tid(Id.editorConfirmKeep)).element)

    await w.get(tid(Id.editorConfirmKeep)).trigger('click')
    expect(w.find(tid(Id.editorConfirm)).exists()).toBe(false)
    expect((field(w, 'name').element as HTMLInputElement).value).toBe('Geändert')

    await w.get('[role="dialog"]').trigger('keydown', { key: 'Escape' })
    expect(w.emitted('update:open')).toBeUndefined()
    await w.get(tid(Id.editorConfirmDiscard)).trigger('click')
    expect(w.emitted('update:open')).toEqual([[false]])
  })

  it('Escape bei offener Rückfrage bricht nur die Rückfrage ab', async () => {
    const w = mountEditor()
    await field(w, 'name').setValue('x')
    await w.get('[role="dialog"]').trigger('keydown', { key: 'Escape' })
    expect(w.find(tid(Id.editorConfirm)).exists()).toBe(true)
    await w.get('[role="dialog"]').trigger('keydown', { key: 'Escape' })
    expect(w.find(tid(Id.editorConfirm)).exists()).toBe(false)
    expect(w.emitted('update:open')).toBeUndefined()
  })
})

describe('PersonaEditorDialog: Herkunftsmarke', () => {
  it.each([
    ['graph', 'aus Graph', 'Aus dem Graphen'],
    ['manual', 'von Hand', 'Von Hand'],
    ['ai_draft', 'KI-Entwurf', 'Entwurf'],
    ['fallback', 'Fallback', 'Degradation'],
  ] as const)('%s trägt Marke und Hinweis', (origin, label, note) => {
    const w = mountEditor({ entry: entry(origin) })
    expect(w.get(tid(Id.editorOrigin)).text()).toContain(label)
    expect(w.get(tid(Id.editorOriginNote)).text()).toContain(note)
  })

  it('neue Personas gelten als von Hand angelegt', () => {
    const w = mountEditor()
    expect(w.get(tid(Id.editorOrigin)).attributes('data-origin')).toBe('manual')
  })
})

describe('Fokus', () => {
  it('fokussiert beim Öffnen das Namensfeld und gibt den Fokus beim Schließen zurück', async () => {
    const opener = document.createElement('button')
    document.body.appendChild(opener)
    opener.focus()
    const w = mountEditor()
    await w.vm.$nextTick()
    await w.vm.$nextTick()
    expect(document.activeElement).toBe(field(w, 'name').element)
    await w.setProps({ open: false })
    await w.vm.$nextTick()
    await w.vm.$nextTick()
    expect(document.activeElement).toBe(opener)
    opener.remove()
  })
})

describe('Vertragsabgleich', () => {
  it('ordnet jedes Vertragsfeld genau einem Abschnitt zu', () => {
    const fields = Object.keys(PersonaSetProfileInputSchema.shape).sort()
    expect(Object.keys(FIELD_SECTION).sort()).toEqual(fields)
  })

  it('PROFILE_LIMITS stimmen mit dem Schema überein', () => {
    const base = { username: 'u', name: 'n' }
    const ok = (extra: Record<string, unknown>) => PersonaSetProfileInputSchema.safeParse({ ...base, ...extra }).success
    expect(ok({ username: 'x'.repeat(PROFILE_LIMITS.username) })).toBe(true)
    expect(ok({ username: 'x'.repeat(PROFILE_LIMITS.username + 1) })).toBe(false)
    expect(ok({ name: 'x'.repeat(PROFILE_LIMITS.name + 1) })).toBe(false)
    expect(ok({ bio: 'x'.repeat(PROFILE_LIMITS.bio) })).toBe(true)
    expect(ok({ bio: 'x'.repeat(PROFILE_LIMITS.bio + 1) })).toBe(false)
    expect(ok({ persona: 'x'.repeat(PROFILE_LIMITS.persona) })).toBe(true)
    expect(ok({ persona: 'x'.repeat(PROFILE_LIMITS.persona + 1) })).toBe(false)
    expect(ok({ age: PROFILE_LIMITS.ageMax })).toBe(true)
    expect(ok({ age: PROFILE_LIMITS.ageMax + 1 })).toBe(false)
    expect(ok({ interested_topics: Array(PROFILE_LIMITS.topics).fill('t') })).toBe(true)
    expect(ok({ interested_topics: Array(PROFILE_LIMITS.topics + 1).fill('t') })).toBe(false)
    expect(ok({ profession: 'x'.repeat(PROFILE_LIMITS.profession + 1) })).toBe(false)
    expect(ok({ source_entity_type: 'x'.repeat(PROFILE_LIMITS.sourceEntityType + 1) })).toBe(false)
    expect(ok({ language: 'x'.repeat(PROFILE_LIMITS.language + 1) })).toBe(false)
    expect(ok({ time_zone: 'x'.repeat(PROFILE_LIMITS.timeZone + 1) })).toBe(false)
    expect(ok({ location: 'x'.repeat(PROFILE_LIMITS.location + 1) })).toBe(false)
  })
})
