import { ref, watch, type Ref } from 'vue'

export type ThemeValue = 'light'

export interface UseThemeReturn {
  theme: Ref<ThemeValue>
  setTheme: (value: ThemeValue) => void
  toggle: () => void
  options: ThemeValue[]
}

const STORAGE_KEY = 'agora-theme'
const VALID: ThemeValue[] = ['light']
const DEFAULT_THEME: ThemeValue = 'light'

function readInitial(): ThemeValue {
  return DEFAULT_THEME
}

const theme = ref<ThemeValue>(readInitial())
let watcherInstalled = false

function applyTheme(value: ThemeValue): void {
  if (typeof document === 'undefined') return
  document.documentElement.setAttribute('data-theme', value)
}

function persist(value: ThemeValue): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY, value)
  } catch {
    /* persistence not available — ignore */
  }
}

function ensureWatcher(): void {
  if (watcherInstalled) return
  watcherInstalled = true
  applyTheme(theme.value)
  watch(theme, (next) => {
    applyTheme(next)
    persist(next)
  })
}

export function useTheme(): UseThemeReturn {
  ensureWatcher()

  function setTheme(value: ThemeValue): void {
    if (!VALID.includes(value)) return
    theme.value = value
  }

function toggle(): void {
    theme.value = DEFAULT_THEME
  }

  return { theme, setTheme, toggle, options: VALID.slice() }
}

export const THEME_STORAGE_KEY = STORAGE_KEY
