/**
 * Test-IDs der Personasatz-Bibliothek (#1807, Etappe 7). Die Wurzel-, Lade-,
 * Fehler- und Leer-IDs bleiben in `PersonaSetTestId` (`contracts/testIds`).
 */
export const PersonaSetLibraryTestId = {
  grid: 'persona-sets-grid',
  tile: 'persona-set-tile',
  tileOpen: 'persona-set-open',
  tileDuplicate: 'persona-set-duplicate',
  tileDelete: 'persona-set-delete',
  tileLocked: 'persona-set-tile-locked',
  importedNote: 'persona-set-imported-note',
  search: 'persona-sets-search',
  noMatches: 'persona-sets-no-matches',
  newButton: 'persona-sets-new',
  emptyNew: 'persona-sets-empty-new',
  createName: 'persona-set-create-name',
  createDescription: 'persona-set-create-description',
  createNameError: 'persona-set-create-name-error',
  createSubmit: 'persona-set-create-submit',
  createCancel: 'persona-set-create-cancel',
  removeConfirm: 'persona-set-remove-confirm',
  removeCancel: 'persona-set-remove-cancel',
  status: 'persona-sets-status',
  actionError: 'persona-sets-action-error',
} as const

/** Kennung des Sammelsatzes „Importiert“ (Backend: `pset_importiert`). */
export const IMPORTED_PERSONA_SET_ID = 'pset_importiert'
