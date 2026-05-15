/**
 * useSidebarState — Group-Expand-State mit localStorage-Persistenz.
 * Modul-globaler Singleton-State: alle Caller teilen dieselbe reaktive Instanz.
 * Storage-Key: agora.sidebar.v1
 */
import { reactive } from 'vue'

const STORAGE_KEY = 'agora.sidebar.v1'
type GroupState = Record<string, boolean>

function hydrate(): GroupState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {}
    const clean: GroupState = {}
    for (const [k, v] of Object.entries(parsed)) {
      if (typeof v === 'boolean') clean[k] = v
    }
    return clean
  } catch {
    return {}
  }
}

function persist(state: GroupState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...state }))
  } catch {
    /* quota / private browsing */
  }
}

// Modul-globaler Singleton-State (einmalig initialisiert, wie in useDensity.ts)
const _state = reactive<GroupState>(hydrate())

export function useSidebarState() {
  return {
    isGroupOpen: (key: string): boolean => _state[key] === true,
    setGroupOpen: (key: string, open: boolean): void => {
      _state[key] = open
      persist(_state)
    },
    toggleGroup: (key: string): void => {
      _state[key] = !_state[key]
      persist(_state)
    },
  }
}

/**
 * Nur für Tests: setzt den Singleton-State zurück und hydriert aus localStorage.
 * @internal — nicht in Produktions-Code aufrufen.
 */
useSidebarState._resetForTesting = function (): void {
  // Alten State löschen
  for (const key of Object.keys(_state)) {
    delete _state[key]
  }
  // Neu aus localStorage hydrieren (sodass Tests localStorage-Fixtures setzen können)
  const fresh = hydrate()
  for (const [k, v] of Object.entries(fresh)) {
    _state[k] = v
  }
}
