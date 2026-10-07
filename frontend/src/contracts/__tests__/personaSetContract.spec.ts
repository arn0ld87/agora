import { describe, expect, it } from 'vitest'
import {
  CreateFromPersonasRequestSchema,
  PersonaOriginSchema,
  PersonaSetCreateSchema,
  PersonaSetEntriesDeleteResponseSchema,
  PersonaSetEntriesDeleteSchema,
  PersonaSetEntryCreateSchema,
  PersonaSetEntrySchema,
  PersonaSetEntryUpdateSchema,
  PersonaSetListResponseSchema,
  PersonaSetProfileInputSchema,
  PersonaSetProfileSchema,
  PersonaSetQualityIssueSchema,
  PersonaSetQualityPersonaSchema,
  PersonaSetQualityReportSchema,
  PersonaSetQualitySummarySchema,
  PersonaSetRecordSchema,
  PersonaSetSummarySchema,
  PersonaSetUpdateSchema,
} from '../personaSetContract'
import createSchema from '../../../../schemas/persona-set-create.schema.json'
import entrySchema from '../../../../schemas/persona-set-entry.schema.json'
import entryCreateSchema from '../../../../schemas/persona-set-entry-create.schema.json'
import entryUpdateSchema from '../../../../schemas/persona-set-entry-update.schema.json'
import entriesDeleteSchema from '../../../../schemas/persona-set-entries-delete.schema.json'
import entriesDeleteResponseSchema from '../../../../schemas/persona-set-entries-delete-response.schema.json'
import listSchema from '../../../../schemas/persona-set-list-response.schema.json'
import profileSchema from '../../../../schemas/persona-set-profile.schema.json'
import qualityIssueSchema from '../../../../schemas/persona-set-quality-issue.schema.json'
import qualityPersonaSchema from '../../../../schemas/persona-set-quality-persona.schema.json'
import qualityReportSchema from '../../../../schemas/persona-set-quality-report.schema.json'
import qualitySummarySchema from '../../../../schemas/persona-set-quality-summary.schema.json'
import recordSchema from '../../../../schemas/persona-set-record.schema.json'
import summarySchema from '../../../../schemas/persona-set-summary.schema.json'
import updateSchema from '../../../../schemas/persona-set-update.schema.json'

const keys = (o: { shape: Record<string, unknown> }): string[] => Object.keys(o.shape).sort()
const props = (s: { properties: Record<string, unknown> }): string[] => Object.keys(s.properties).sort()

const PROFILE = {
  username: 'anna', name: 'Anna', bio: '', persona: '', age: null, gender: null, mbti: null,
  country: null, profession: null, interested_topics: [], source_entity_type: null,
  persona_kind: 'individual', language: null, activity_level: null, time_zone: null,
  location: null, verified: false,
}
const ENTRY = {
  entry_id: 'e1', origin: 'manual', profile: PROFILE, source_entity_uuid: null,
  created_at: '2026-10-07T10:00:00', updated_at: '2026-10-07T10:00:00',
}
const SUMMARY = {
  id: 's1', name: 'Satz', description: '', graph_id: null, project_id: null, entry_count: 1,
  locked: false, locked_at: null, usage_count: 0,
  created_at: '2026-10-07T10:00:00', updated_at: '2026-10-07T10:00:00', schema_version: 1,
}
const RECORD = {
  id: 's1', name: 'Satz', description: '', graph_id: null, project_id: null, entries: [ENTRY],
  locked_at: null, used_by_simulation_ids: [],
  created_at: '2026-10-07T10:00:00', updated_at: '2026-10-07T10:00:00', schema_version: 1,
}

describe('personaSetContract: Felder deckungsgleich mit den generierten Schemas', () => {
  it.each([
    ['Profil', keys(PersonaSetProfileSchema), props(profileSchema)],
    ['Eintrag', keys(PersonaSetEntrySchema), props(entrySchema)],
    ['Record', keys(PersonaSetRecordSchema as unknown as { shape: Record<string, unknown> }), props(recordSchema)],
    ['Summary', keys(PersonaSetSummarySchema), props(summarySchema)],
    ['Create', keys(PersonaSetCreateSchema), props(createSchema)],
    ['Update', keys(PersonaSetUpdateSchema as unknown as { shape: Record<string, unknown> }), props(updateSchema)],
    ['EntryCreate', keys(PersonaSetEntryCreateSchema), props(entryCreateSchema)],
    ['EntryUpdate', keys(PersonaSetEntryUpdateSchema as unknown as { shape: Record<string, unknown> }), props(entryUpdateSchema)],
    ['EntriesDelete', keys(PersonaSetEntriesDeleteSchema), props(entriesDeleteSchema)],
    ['EntriesDeleteResponse', keys(PersonaSetEntriesDeleteResponseSchema), props(entriesDeleteResponseSchema)],
    ['ListResponse', keys(PersonaSetListResponseSchema), props(listSchema)],
    ['QualityIssue', keys(PersonaSetQualityIssueSchema), props(qualityIssueSchema)],
    ['QualityPersona', keys(PersonaSetQualityPersonaSchema), props(qualityPersonaSchema)],
    ['QualitySummary', keys(PersonaSetQualitySummarySchema), props(qualitySummarySchema)],
    ['QualityReport', keys(PersonaSetQualityReportSchema), props(qualityReportSchema)],
  ])('%s', (_name, zodKeys, jsonKeys) => {
    expect(zodKeys).toEqual(jsonKeys)
  })

  it('Herkunft und Profil-Enums stimmen mit dem Schema überein', () => {
    const originEnum = (entrySchema.properties.origin as unknown as { $ref?: string; enum?: string[] })
    const resolved = originEnum.enum ?? (entrySchema as unknown as { $defs: Record<string, { enum: string[] }> }).$defs.PersonaOrigin?.enum
    if (resolved) expect(PersonaOriginSchema.options).toEqual(resolved)
    expect(PersonaOriginSchema.options).toEqual(['graph', 'manual', 'ai_draft', 'fallback'])
  })
})

describe('personaSetContract: Antworten', () => {
  it('liest Satz, Kachel, Liste und Qualitätsbericht', () => {
    expect(PersonaSetRecordSchema.parse(RECORD).entries[0].origin).toBe('manual')
    expect(PersonaSetListResponseSchema.parse({ count: 1, sets: [SUMMARY] }).sets).toHaveLength(1)
    const q = PersonaSetQualityReportSchema.parse({
      set_id: 's1',
      summary: { total: 1, role_diversity: 0.5, mbti_diversity: 0, distinct_roles: [], distinct_mbti: [] },
      global_issues: [{ code: 'x', severity: 'warning', detail: null }],
      personas: [{ entry_id: 'e1', username: 'anna', issues: [{ code: 'y', severity: 'info' }] }],
    })
    expect(q.global_issues[0].severity).toBe('warning')
  })

  it('verwirft eine unbekannte Herkunft, ein unbekanntes Feld und einen gesperrten Satz ohne locked_at', () => {
    expect(PersonaSetEntrySchema.safeParse({ ...ENTRY, origin: 'import' }).success).toBe(false)
    expect(PersonaSetSummarySchema.safeParse({ ...SUMMARY, extra: 1 }).success).toBe(false)
    expect(PersonaSetRecordSchema.safeParse({ ...RECORD, used_by_simulation_ids: ['sim_1'] }).success).toBe(false)
    expect(
      PersonaSetRecordSchema.safeParse({
        ...RECORD, used_by_simulation_ids: ['sim_1'], locked_at: '2026-10-07T11:00:00',
      }).success,
    ).toBe(true)
  })
})

describe('personaSetContract: Anfragen', () => {
  it('Profil: nur username und name sind Pflicht, Vorgaben werden ergänzt', () => {
    const p = PersonaSetProfileInputSchema.parse({ username: 'a', name: 'A' })
    expect(p.persona_kind).toBe('individual')
    expect(p.interested_topics).toEqual([])
    expect(PersonaSetProfileInputSchema.safeParse({ username: 'a' }).success).toBe(false)
    expect(PersonaSetProfileInputSchema.safeParse({ username: 'a', name: 'A', mbti: 'XXXX' }).success).toBe(false)
    expect(PersonaSetProfileInputSchema.safeParse({ username: 'a', name: 'A', country: 'DEU' }).success).toBe(false)
  })

  it('Update-Anfragen verlangen mindestens ein Feld', () => {
    expect(PersonaSetUpdateSchema.safeParse({}).success).toBe(false)
    expect(PersonaSetUpdateSchema.safeParse({ name: 'Neu' }).success).toBe(true)
    expect(PersonaSetEntryUpdateSchema.safeParse({}).success).toBe(false)
    expect(PersonaSetEntryUpdateSchema.safeParse({ origin: 'fallback' }).success).toBe(true)
  })

  it('Name wird getrimmt, leer abgelehnt; Mehrfachlöschen verlangt Kennungen', () => {
    expect(PersonaSetCreateSchema.parse({ name: '  Satz ' }).name).toBe('Satz')
    expect(PersonaSetCreateSchema.safeParse({ name: '   ' }).success).toBe(false)
    expect(PersonaSetEntriesDeleteSchema.safeParse({ entry_ids: [] }).success).toBe(false)
  })

  it('create-from-personas: genau eine Quelle', () => {
    expect(CreateFromPersonasRequestSchema.safeParse({ simulation_requirement: 'x', persona_set_id: 's1' }).success).toBe(true)
    expect(
      CreateFromPersonasRequestSchema.safeParse({ simulation_requirement: 'x', template_ids: ['a'] }).success,
    ).toBe(true)
    expect(
      CreateFromPersonasRequestSchema.safeParse({ simulation_requirement: 'x', persona_set_id: 's1', template_ids: ['a'] })
        .success,
    ).toBe(false)
    expect(
      CreateFromPersonasRequestSchema.safeParse({ simulation_requirement: 'x', persona_set_id: 's1', personas: [] }).success,
    ).toBe(true)
    expect(CreateFromPersonasRequestSchema.safeParse({ simulation_requirement: 'x', persona_set_id: ' ' }).success).toBe(false)
  })
})
