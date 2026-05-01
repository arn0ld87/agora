import { ref, watch } from 'vue'

const STORAGE_KEY = 'agora-theme'
const VALID = ['light', 'dark']
const DEFAULT_THEME = 'light'

function readInitial() {
  if (typeof document !== 'undefined') {
    const attr = document.documentElement.getAttribute('data-theme')
    if (VALID.includes(attr)) return attr
  }
  if (typeof localStorage !== 'undefined') {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (VALID.includes(stored)) return stored
    } catch {
      /* localStorage blocked */
    }
  }
  return DEFAULT_THEME
}

const theme = ref(readInitial())
let watcherInstalled = false

function applyTheme(value) {
  if (typeof document === 'undefined') return
  document.documentElement.setAttribute('data-theme', value)
}

function persist(value) {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY, value)
  } catch {
    /* persistence not available — ignore */
  }
}

function ensureWatcher() {
  if (watcherInstalled) return
  watcherInstalled = true
  applyTheme(theme.value)
  watch(theme, (next) => {
    applyTheme(next)
    persist(next)
  })
}

export function useTheme() {
  ensureWatcher()

  function setTheme(value) {
    if (!VALID.includes(value)) return
    theme.value = value
  }

  function toggle() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }

  return { theme, setTheme, toggle, options: VALID.slice() }
}

export const THEME_STORAGE_KEY = STORAGE_KEY
