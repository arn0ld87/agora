/**
 * useSidebarState — Group-Expand-State mit localStorage-Persistenz.
 * Jeder Aufruf erstellt einen frischen reaktiven State, der aus localStorage
 * hydriert wird und Änderungen synchron zurückschreibt.
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

export function useSidebarState() {
  const state = reactive<GroupState>(hydrate())

  return {
    isGroupOpen: (key: string): boolean => state[key] === true,
    setGroupOpen: (key: string, open: boolean): void => {
      state[key] = open
      persist(state)
    },
    toggleGroup: (key: string): void => {
      state[key] = !state[key]
      persist(state)
    },
  }
}
