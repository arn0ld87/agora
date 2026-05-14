import { z } from 'zod'

export const SettingsSectionSchema = z.enum([
  'llm',
  'neo4j',
  'embedding',
  'ontology',
  'hybrid_search',
  'agent_tools',
  'event_bus',
  'logging',
  'locale',
  'ui',
  'webtools',
  'oasis',
  'security',
])
export type SettingsSection = z.infer<typeof SettingsSectionSchema>

export const SettingsFieldTypeSchema = z.enum(['string', 'int', 'float', 'bool', 'enum'])
export type SettingsFieldType = z.infer<typeof SettingsFieldTypeSchema>

export const SettingsFieldSourceSchema = z.enum(['default', 'env', 'file', 'override'])
export type SettingsFieldSource = z.infer<typeof SettingsFieldSourceSchema>

export const SettingsFieldSpecSchema = z.object({
  key: z.string().min(1),
  section: SettingsSectionSchema,
  type: SettingsFieldTypeSchema,
  secret: z.boolean(),
  reload_required: z.boolean(),
  default: z.unknown().optional(),
  enum_values: z.array(z.string()).optional(),
  min: z.number().optional(),
  max: z.number().optional(),
  cross_validates_with: z.array(z.string()).optional(),
}).strict()
export type SettingsFieldSpec = z.infer<typeof SettingsFieldSpecSchema>

export const SettingsFieldMetaSchema = z.object({
  key: z.string().min(1),
  section: SettingsSectionSchema,
  type: SettingsFieldTypeSchema,
  secret: z.boolean(),
  reload_required: z.boolean(),
  source: SettingsFieldSourceSchema,
  is_set: z.boolean(),
  value: z.unknown().optional(),
  default: z.unknown().optional(),
  enum_values: z.array(z.string()).optional(),
}).strict()
export type SettingsFieldMeta = z.infer<typeof SettingsFieldMetaSchema>

export const SettingsValuesPayloadSchema = z.object({
  sections: z.array(SettingsSectionSchema),
  fields: z.record(z.string(), z.array(SettingsFieldMetaSchema)),
  updated_keys: z.array(z.string()).optional(),
}).strict()
export type SettingsValuesPayload = z.infer<typeof SettingsValuesPayloadSchema>

export const SettingsSchemaPayloadSchema = z.object({
  sections: z.array(SettingsSectionSchema),
  fields: z.array(SettingsFieldSpecSchema),
}).strict()
export type SettingsSchemaPayload = z.infer<typeof SettingsSchemaPayloadSchema>

export const SettingsEnvelopeSchema = z.object({
  success: z.literal(true),
  data: SettingsValuesPayloadSchema,
}).strict()
export type SettingsEnvelope = z.infer<typeof SettingsEnvelopeSchema>

export const SettingsSchemaEnvelopeSchema = z.object({
  success: z.literal(true),
  data: SettingsSchemaPayloadSchema,
}).strict()
export type SettingsSchemaEnvelope = z.infer<typeof SettingsSchemaEnvelopeSchema>

export const SettingsChangedEventSchema = z.object({
  type: z.literal('settings.changed'),
  updated_keys: z.array(z.string()),
  ts: z.string(),
}).strict()
export type SettingsChangedEvent = z.infer<typeof SettingsChangedEventSchema>

export function parseSettingsEnvelope(raw: unknown) {
  return SettingsEnvelopeSchema.safeParse(raw)
}

export function parseSettingsSchemaEnvelope(raw: unknown) {
  return SettingsSchemaEnvelopeSchema.safeParse(raw)
}

export function parseSettingsChangedEvent(raw: unknown) {
  return SettingsChangedEventSchema.safeParse(raw)
}
