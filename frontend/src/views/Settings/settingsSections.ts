import type { SettingsSection } from '@/contracts/settingsContract'

export const GENERAL_SETTINGS_SECTIONS = [
  'logging',
  'locale',
  'ui',
  'event_bus',
  'security',
] as const satisfies readonly SettingsSection[]

/** `llm` wandert mit dem Einstellungsfenster von „Allgemein“ zu „Profile“. */
export const PROFILE_SETTINGS_SECTIONS = ['llm'] as const satisfies readonly SettingsSection[]

export const INTEGRATION_SETTINGS_SECTIONS = [
  'neo4j',
  'embedding',
  'ontology',
  'hybrid_search',
  'agent_tools',
  'webtools',
  'oasis',
  'budget',
] as const satisfies readonly SettingsSection[]
