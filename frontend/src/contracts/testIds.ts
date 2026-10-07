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
// Fix #1713: SettingsOverlay ist ein reiner Layout-Wrapper ohne eigene Nav
// (die Sidebar-Gruppe „Einstellungen” ist die einzige Navigationsebene) —
// nur noch der Root-Marker bleibt.
export const SettingsOverlayTestId = {
  root: 'settings-overlay',
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
  sessionNotice: 'llm-provider-session-notice',
  cliKeyHint: 'llm-provider-cli-key-hint',
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
  // Issue #1477 F2: Vertrauenswarnung, wenn die Evidence-Map degradiert ist.
  evidenceOmittedWarning: 'dossier-evidence-omitted-warning',
} as const

/**
 * RunReportTestId — Bericht als Reiter am Lauf (Etappe 5, #1804). Loest die
 * Selektoren der alten Leseumgebung (`ReportReaderTestId`) ab. Die Eintraege
 * stehen als Literale in `components/run/report/**`; `ReportTestIds.spec.ts`
 * prueft, dass beides uebereinstimmt.
 *   outline          Gliederung (nav)
 *   outlineItemPrefix  Eintrag je Abschnitt: `report-outline-item-<n>`
 *   text             Lesetext (article), gespeicherte Berichte als ein Block
 *   claim            ein Claim der Claim-Liste in der Belegspalte
 *   evidencePanel    Belegspalte (Kennzahlen, Belege, Claims, Pruefhinweise)
 */
export const RunReportTestId = {
  outline: 'report-outline',
  outlineItemPrefix: 'report-outline-item-',
  text: 'report-text',
  claim: 'report-claim',
  evidencePanel: 'report-evidence-panel',
} as const

/**
 * SimulationLiveTestId — Selektoren fuer die Simulation-live-Instrument-
 * Ansicht (Redesign PR 7, Audit §5 "Simulation live"). Kopfzeile,
 * Rundenachse, die vier Bahnen (Akteure/Reddit/Twitter/System) und die
 * Eingriffs-Aktionen (Pause/Fortsetzen, Abbrechen).
 */
export const SimulationLiveTestId = {
  root: 'sim-live-root',
  headerRound: 'sim-live-header-round',
  headerElapsed: 'sim-live-header-elapsed',
  headerSecPerRound: 'sim-live-header-sec-per-round',
  headerPauseResume: 'sim-live-header-pause-resume',
  headerCancel: 'sim-live-header-cancel',
  roundAxis: 'sim-live-round-axis',
  roundTick: 'sim-live-round-tick',
  laneActors: 'sim-live-lane-actors',
  actorRow: 'sim-live-actor-row',
  laneReddit: 'sim-live-lane-reddit',
  laneTwitter: 'sim-live-lane-twitter',
  laneSystem: 'sim-live-lane-system',
  eventRow: 'sim-live-event-row',
} as const

export type SimulationLiveTestId = (typeof SimulationLiveTestId)[keyof typeof SimulationLiveTestId]

/**
 * ShelfTableTestId — Tabellenmodus der Ablage (Redesign PR 8, Audit §7
 * "Läufe (/runs)"). Ergaenzt `ShelfTestId` um den Umschalter Liste⇄Tabelle
 * und die DataTable-Instanz fuer die Filter „lauf"/„jobs". Die Tabelle
 * selbst (Kopf/Zeilen/Zellen) nutzt `DataTable.vue` — hier stehen nur die
 * Shelf-eigenen Selektoren (Umschalter, Wrapper, Vergleichen-Aktion).
 */
export const ShelfTableTestId = {
  toggle: 'shelf-table-toggle',
  toggleList: 'shelf-table-toggle-list',
  toggleTable: 'shelf-table-toggle-table',
  root: 'shelf-table-root',
  compareAction: 'shelf-table-compare-action',
} as const

export type ShelfTableTestId = (typeof ShelfTableTestId)[keyof typeof ShelfTableTestId]

/**
 * PersonaSetTestId — Personasätze (#1807, Etappe 7): Bibliothek, Detailansicht
 * und Reiter „Personas“ am Lauf. Das Skelett zeigt Überschrift, Lade-, Fehler-
 * und Leerzustand; die Folgetickets hängen ihre Elemente an dieselben Wurzeln.
 */
export const PersonaSetTestId = {
  libraryRoot: 'persona-sets-library',
  detailRoot: 'persona-set-detail',
  runRoot: 'run-personas',
  loading: 'persona-sets-loading',
  error: 'persona-sets-error',
  empty: 'persona-sets-empty',
  locked: 'persona-set-locked',
} as const

export type PersonaSetTestId = (typeof PersonaSetTestId)[keyof typeof PersonaSetTestId]
