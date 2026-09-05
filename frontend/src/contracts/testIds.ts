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

export const LlmRoutingTestId = {
  runId: 'llm-routing-run-id',
  stageRow: 'llm-routing-stage-row',
  stageSave: 'stage-override-save',
} as const

export type LlmRoutingTestId = (typeof LlmRoutingTestId)[keyof typeof LlmRoutingTestId]

/**
 * Block B3 — Neuhuelle „Richtung B · Dossier“.
 *
 * Testid-Kontrakt VOR den Komponenten angelegt (PLAN.md, B3): der alte
 * Shell-Bereich hatte keinen — Tests hingen an CSS-Klassen wie
 * `.topbar__hamburger` und brachen bei jeder Umbenennung. Die neuen
 * Komponenten und ihre Specs greifen beide auf DIESE Konstanten zu.
 */
export const ShellTestId = {
  root: 'shell-root',
  stack: 'shell-stack',
  stackBack: 'shell-stack-back',
  userMenu: 'shell-user-menu',
  userMenuButton: 'shell-user-menu-button',
  activityIndicator: 'shell-activity-indicator',
  activityCancel: 'shell-activity-cancel',
  undoToast: 'shell-undo-toast',
  undoButton: 'shell-undo-button',
  // Block B4 (Mobile 390px): ⌘K-Knopf verschwindet unter dem Schmal-
  // Breakpoint ganz aus dem Markup (nicht nur CSS-versteckt) — braucht
  // deshalb eine eigene testid, um das in Komponenten-Tests zu pruefen.
  cmdkTrigger: 'shell-cmdk-trigger',
  // Redesign PR 2 (Chrome bereinigen): Log-Drawer wandert von der globalen
  // FAB (App.vue) in ein Kopfzeilen-Icon — in BEIDEN Huellen unter dieser ID.
  logsTrigger: 'shell-logs-trigger',
  panelShelf: 'shell-panel-shelf',
  panelDossier: 'shell-panel-dossier',
} as const

export const ShelfTestId = {
  root: 'shelf-root',
  filter: 'shelf-filter',
  filterPill: 'shelf-filter-pill',
  row: 'shelf-row',
  rowTag: 'shelf-row-tag',
  rowTitle: 'shelf-row-title',
  rowStatus: 'shelf-row-status',
  rowNextAction: 'shelf-row-next-action',
  rowCancel: 'shelf-row-cancel',
  rowPause: 'shelf-row-pause',
  rowPersonaError: 'shelf-row-persona-error',
  jobsTable: 'shelf-jobs-table',
  empty: 'shelf-empty',
  newObject: 'shelf-new-object',
} as const

export const DossierTestId = {
  root: 'dossier-root',
  title: 'dossier-title',
  summary: 'dossier-summary',
  kpis: 'dossier-kpis',
  parts: 'dossier-parts',
  part: 'dossier-part',
  openFull: 'dossier-open-full',
  derive: 'dossier-derive',
  startFromPersona: 'dossier-start-from-persona',
  cancel: 'dossier-cancel',
  pause: 'dossier-pause',
  overview: 'dossier-overview',
  overviewNewSource: 'dossier-overview-new-source',
  overviewAttentionItem: 'dossier-overview-attention-item',
  overviewLiveItem: 'dossier-overview-live-item',
  overviewRecentItem: 'dossier-overview-recent-item',
  overviewSystemRow: 'dossier-overview-system-row',
} as const
