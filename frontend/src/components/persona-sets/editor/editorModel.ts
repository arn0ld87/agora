/**
 * Formularmodell des Persona-Editors (#1807, E7-F3).
 *
 * Der Entwurf hält alles als Text/Bool, damit Eingabefelder direkt binden; `toInput`
 * baut daraus die Eingabeform für `PersonaSetProfileInputSchema`, `validateDraft`
 * prüft sie gegen den Vertrag. Die Zuordnung Feld -> Abschnitt ist über `satisfies`
 * vollständig erzwungen: ein neues Vertragsfeld ohne Abschnitt bricht den Typcheck.
 */
import type { ZodIssue } from 'zod'
import {
  PersonaSetProfileInputSchema,
  type PersonaSetProfile,
  type PersonaSetProfileInput,
} from '@/contracts/personaSetContract'

export const EDITOR_SECTIONS = ['identity', 'stance', 'language', 'activity', 'graph'] as const
export type EditorSectionId = (typeof EDITOR_SECTIONS)[number]

/** Grenzen des Vertrags (`personaSetContract.ts`); `editorModel.spec.ts` gleicht sie mit dem Schema ab. */
export const PROFILE_LIMITS = {
  username: 64,
  name: 120,
  bio: 500,
  persona: 12000,
  ageMax: 120,
  country: 2,
  profession: 200,
  topics: 15,
  sourceEntityType: 120,
  language: 16,
  timeZone: 64,
  location: 200,
} as const

type ProfileField = keyof PersonaSetProfile

/** Jedes Vertragsfeld liegt in genau einem Abschnitt. */
export const FIELD_SECTION = {
  name: 'identity',
  username: 'identity',
  persona_kind: 'identity',
  profession: 'identity',
  age: 'identity',
  gender: 'identity',
  country: 'identity',
  location: 'identity',
  bio: 'identity',
  verified: 'identity',
  persona: 'stance',
  interested_topics: 'stance',
  mbti: 'stance',
  language: 'language',
  activity_level: 'activity',
  time_zone: 'activity',
  source_entity_type: 'graph',
} as const satisfies Record<ProfileField, EditorSectionId>

/** Reihenfolge der Felder für „erster Fehler“ und Zusammenfassung. */
export const FIELD_ORDER = Object.keys(FIELD_SECTION) as ProfileField[]

export interface EditorDraft {
  name: string
  username: string
  bio: string
  persona: string
  age: string
  gender: string
  mbti: string
  country: string
  profession: string
  /** Ein Thema pro Zeile. */
  topics: string
  source_entity_type: string
  persona_kind: string
  language: string
  activity_level: string
  time_zone: string
  location: string
  verified: boolean
}

export function emptyDraft(): EditorDraft {
  return {
    name: '', username: '', bio: '', persona: '', age: '', gender: '', mbti: '', country: '',
    profession: '', topics: '', source_entity_type: '', persona_kind: 'individual', language: '',
    activity_level: '', time_zone: '', location: '', verified: false,
  }
}

export function draftFromProfile(p: PersonaSetProfile): EditorDraft {
  return {
    name: p.name,
    username: p.username,
    bio: p.bio,
    persona: p.persona,
    age: p.age === null ? '' : String(p.age),
    gender: p.gender ?? '',
    mbti: p.mbti ?? '',
    country: p.country ?? '',
    profession: p.profession ?? '',
    topics: p.interested_topics.join('\n'),
    source_entity_type: p.source_entity_type ?? '',
    persona_kind: p.persona_kind,
    language: p.language ?? '',
    activity_level: p.activity_level === null ? '' : String(p.activity_level),
    time_zone: p.time_zone ?? '',
    location: p.location ?? '',
    verified: p.verified,
  }
}

function orNull(value: string): string | null {
  const v = value.trim()
  return v === '' ? null : v
}

function numberOrNull(value: string): number | null {
  const v = value.trim().replace(',', '.')
  return v === '' ? null : Number(v)
}

/** Eingabeform für den Vertrag; ungültige Werte (z. B. NaN) lässt das Schema scheitern. */
export function toInput(d: EditorDraft): Record<string, unknown> {
  return {
    username: d.username.trim(),
    name: d.name.trim(),
    bio: d.bio,
    persona: d.persona,
    age: numberOrNull(d.age),
    gender: orNull(d.gender),
    mbti: orNull(d.mbti),
    country: orNull(d.country),
    profession: orNull(d.profession),
    interested_topics: d.topics.split('\n').map((s) => s.trim()).filter((s) => s !== ''),
    source_entity_type: orNull(d.source_entity_type),
    persona_kind: d.persona_kind,
    language: orNull(d.language),
    activity_level: numberOrNull(d.activity_level),
    time_zone: orNull(d.time_zone),
    location: orNull(d.location),
    verified: d.verified,
  }
}

export type FieldErrorKey = 'required' | 'tooLong' | 'tooMany' | 'range' | 'countryCode' | 'wholeNumber' | 'number' | 'invalid'

export interface FieldError {
  key: FieldErrorKey
  params: Record<string, number>
}

/** Übersetzte Fehlertexte je Feld, wie sie die Abschnitte anzeigen. */
export type FieldMessages = Partial<Record<ProfileField, string>>

export type DraftErrors =Partial<Record<ProfileField, FieldError>>

function toFieldError(field: ProfileField, issue: ZodIssue): FieldError {
  const none: Record<string, number> = {}
  if (field === 'country') {
    return issue.code === 'too_small' || issue.code === 'too_big'
      ? { key: 'countryCode', params: none }
      : { key: 'invalid', params: none }
  }
  if (field === 'age') {
    if (issue.code === 'too_small' || issue.code === 'too_big') {
      return { key: 'range', params: { min: 0, max: PROFILE_LIMITS.ageMax } }
    }
    return { key: 'wholeNumber', params: none }
  }
  if (field === 'activity_level') {
    if (issue.code === 'too_small' || issue.code === 'too_big') return { key: 'range', params: { min: 0, max: 1 } }
    return { key: 'number', params: none }
  }
  if (issue.code === 'too_small') return { key: 'required', params: none }
  if (issue.code === 'too_big') {
    const max = Number((issue as { maximum?: number | bigint }).maximum ?? 0)
    return { key: field === 'interested_topics' ? 'tooMany' : 'tooLong', params: { max } }
  }
  return { key: 'invalid', params: none }
}

export type DraftValidation =
  | { ok: true; data: PersonaSetProfileInput }
  | { ok: false; errors: DraftErrors; ordered: ProfileField[] }

export function validateDraft(d: EditorDraft): DraftValidation {
  const parsed = PersonaSetProfileInputSchema.safeParse(toInput(d))
  if (parsed.success) return { ok: true, data: parsed.data }
  const errors: DraftErrors = {}
  for (const issue of parsed.error.issues) {
    const field = issue.path[0]
    if (typeof field !== 'string' || !(field in FIELD_SECTION)) continue
    const f = field as ProfileField
    if (!errors[f]) errors[f] = toFieldError(f, issue)
  }
  return { ok: false, errors, ordered: FIELD_ORDER.filter((f) => errors[f]) }
}

/** DOM-ID eines Feldes; Kinder und Dialog nutzen dieselbe Ableitung. */
export function fieldDomId(uid: string, field: ProfileField): string {
  return `${uid}-${field}`
}
