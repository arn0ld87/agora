/**
 * Zentrales data-testid-Register fuer E2E + Komponenten-Tests.
 *
 * Single source of truth fuer stabile Test-Selektoren. Sowohl die
 * Vue-Komponenten (data-testid-Attribute) als auch die Playwright-
 * Specs (Locator-Building) greifen auf DIESE Konstanten zu — kein
 * String-Drift zwischen Komponente und Spec.
 *
 * Namensschema: `<namespace>-<element>[-<modifier>]`
 *
 * Slice 5.6-Prep: angelegt fuer AiModelPicker. 5.4 (Migration der
 * Auswahlstellen) und 5.5 (Deprecation) muessen dieselben IDs in
 * den migrierten Views (HeroNewRun, SettingsGeneralView,
 * StepModelOverrideChip) wiederverwenden, damit die Specs ohne
 * Selector-Aenderungen weiterlaufen. Bei neuen Pickern bitte
 * eigenen Namespace waehlen (z. B. `embedding-picker-*`).
 *
 * Kollisionen werden bei Lint-Zeit sichtbar, weil jeder Namespace
 * als eigenes Objekt unter `AiModelPickerTestId` etc. deklariert
 * ist.
 */

export const AiModelPickerTestId = {
  root: 'ai-model-picker',
  input: 'ai-model-picker-input',
  search: 'ai-model-picker-search',
  group: 'ai-model-picker-group',
  option: 'ai-model-picker-option',
  status: 'ai-model-picker-status',
  empty: 'ai-model-picker-empty',
} as const

export type AiModelPickerTestId = (typeof AiModelPickerTestId)[keyof typeof AiModelPickerTestId]
