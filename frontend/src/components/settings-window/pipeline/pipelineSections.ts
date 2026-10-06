import { INTEGRATION_SETTINGS_SECTIONS } from '@/views/Settings/settingsSections'

/**
 * Sektionen des Abschnitts „Pipeline“: die Integrationen ohne `budget`
 * (Budgets haben einen eigenen Fensterabschnitt).
 */
export const PIPELINE_SETTINGS_SECTIONS: readonly string[] = INTEGRATION_SETTINGS_SECTIONS.filter(
  (s) => s !== 'budget',
)
