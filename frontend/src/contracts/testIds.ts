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

/**
 * Redesign PR 9 (`ui(settings)`): Einstellungen-Overlay + Provider-Liste.
 *
 * `SettingsOverlay` ersetzt die Pro-Seite-Breadcrumbs durch eine gemeinsame
 * Sektionsliste; `LlmProviderList*` ersetzt die Card-pro-Provider-Grid aus
 * `LlmProvidersView` durch Liste + Detail-Formular.
 */
export const SettingsOverlayTestId = {
  root: 'settings-overlay',
  nav: 'settings-overlay-nav',
  navItem: 'settings-overlay-nav-item',
  back: 'settings-overlay-back',
} as const

export type SettingsOverlayTestId = (typeof SettingsOverlayTestId)[keyof typeof SettingsOverlayTestId]

export const LlmProviderListTestId = {
  list: 'llm-provider-list',
  row: 'llm-provider-list-row',
  detail: 'llm-provider-detail',
  saveButton: 'llm-provider-save',
  testButton: 'llm-provider-test',
  refreshModelsButton: 'llm-provider-refresh-models',
  disconnectButton: 'llm-provider-disconnect',
} as const

export type LlmProviderListTestId = (typeof LlmProviderListTestId)[keyof typeof LlmProviderListTestId]

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
  jobsTimeline: 'dossier-jobs-timeline',
  confidenceDistribution: 'dossier-confidence-distribution',
  redTeamFindings: 'dossier-red-team-findings',
} as const

/**
 * ReportReaderTestId — PR 6 (Premium-Redesign, "Bericht lesen").
 *
 * Deckt die Dreispalten-Leseumgebung ab (ReportReader.vue + ReportOutline.vue
 * + ReportEvidenceRail.vue): Outline links, Serif-Lesespalte, Belegrand
 * rechts, Overlay "Neu generieren" fuer Modell/Modus.
 */
export const ReportReaderTestId = {
  root: 'report-reader-root',
  outline: 'report-reader-outline',
  outlineItem: 'report-reader-outline-item',
  body: 'report-reader-body',
  section: 'report-reader-section',
  rail: 'report-reader-evidence-rail',
  railToggle: 'report-reader-rail-toggle',
  claim: 'report-reader-claim',
  gap: 'report-reader-gap',
  redTeam: 'report-reader-red-team',
  regenerateOpen: 'report-reader-regenerate-open',
  regenerateOverlay: 'report-reader-regenerate-overlay',
  regenerateClose: 'report-reader-regenerate-close',
  regenerateConfirm: 'report-reader-regenerate-confirm',
} as const

export type ReportReaderTestId = (typeof ReportReaderTestId)[keyof typeof ReportReaderTestId]
