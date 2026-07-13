import type { SettingsSection } from '@/contracts/settingsContract'

export const GENERAL_SETTINGS_SECTIONS = [
  'llm',
  'logging',
  'locale',
  'ui',
  'event_bus',
  'security',
] as const satisfies readonly SettingsSection[]

export const INTEGRATION_SETTINGS_SECTIONS = [
  'neo4j',
  'embedding',
  'ontology',
  'hybrid_search',
  'agent_tools',
  'webtools',
  'oasis',
] as const satisfies readonly SettingsSection[]
