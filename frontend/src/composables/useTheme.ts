/**
 * useTheme — Hell/Dunkel nach System, mit gespeicherter Wahl (#1795, Ticket 3).
 *
 * Single-source-of-truth ist data-theme auf document.documentElement; die
 * Werte je Theme stehen in tokens-umbau.css. Ohne gespeicherte Wahl gilt
 * 'system': die App folgt prefers-color-scheme, auch bei einem Wechsel zur
 * Laufzeit. Eine gespeicherte Wahl gewinnt gegen das System.
 *
 * Persistence: localStorage key 'agora.theme' (Zugriff in try/catch).
 * Kein Aufblitzen: der Inline-Script in index.html setzt data-theme vor dem
 * ersten Paint mit derselben Logik, main.ts ruft useTheme() vor app.mount().
 * Ein Bedienelement gibt es hier noch nicht.
 */

import { computed, readonly, ref, type ComputedRef, type Ref } from 'vue'

export type ThemeChoice = 'system' | 'light' | 'dark'
export type ResolvedTheme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'agora.theme'
const DARK_QUERY = '(prefers-color-scheme: dark)'
const VALID: ReadonlyArray<ThemeChoice> = ['system', 'light', 'dark']

function readStoredChoice(): ThemeChoice {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY)
    if (raw !== null && VALID.includes(raw as ThemeChoice)) return raw as ThemeChoice
  } catch {
    // localStorage kann in bestimmten Kontexten gesperrt sein
  }
  return 'system'
}

function persistChoice(value: ThemeChoice): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, value)
  } catch {
    // Storage gesperrt — kein harter Fehler
  }
}

function getMediaQuery(): MediaQueryList | null {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return null
  return window.matchMedia(DARK_QUERY)
}

function applyToDom(value: ResolvedTheme): void {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.setAttribute('data-theme', value)
  root.style.colorScheme = value
}

interface ThemeState {
  choice: Ref<ThemeChoice>
  systemDark: Ref<boolean>
  resolved: ComputedRef<ResolvedTheme>
  dispose: () => void
}

function createState(): ThemeState {
  const mq = getMediaQuery()
  // Ohne matchMedia (alte Umgebung, Test): dunkel, wie bisher.
  const systemDark = ref<boolean>(mq === null ? true : mq.matches)
  const choice = ref<ThemeChoice>(readStoredChoice())
  const resolved = computed<ResolvedTheme>(() =>
    choice.value === 'system' ? (systemDark.value ? 'dark' : 'light') : choice.value,
  )

  const onChange = (event: MediaQueryListEvent): void => {
    systemDark.value = event.matches
    applyToDom(resolved.value)
  }
  mq?.addEventListener('change', onChange)

  applyToDom(resolved.value)

  return {
    choice,
    systemDark,
    resolved,
    dispose: () => mq?.removeEventListener('change', onChange),
  }
}

// Modul-globaler Singleton-State, beim ersten useTheme()-Aufruf angelegt.
let state: ThemeState | null = null

export function useTheme(): {
  choice: Readonly<Ref<ThemeChoice>>
  resolved: Readonly<Ref<ResolvedTheme>>
  setChoice: (c: ThemeChoice) => void
} {
  if (state === null) state = createState()
  const s = state

  function setChoice(c: ThemeChoice): void {
    if (!VALID.includes(c)) return
    s.choice.value = c
    persistChoice(c)
    applyToDom(s.resolved.value)
  }

  return {
    choice: readonly(s.choice),
    resolved: readonly(s.resolved),
    setChoice,
  }
}

/**
 * Nur für Tests: verwirft den Singleton samt matchMedia-Listener, damit jeder
 * Test mit frisch gelesenem Speicher und System-Zustand startet.
 *
 * @internal — nicht in Produktions-Code aufrufen.
 */
useTheme._resetForTesting = function (): void {
  state?.dispose()
  state = null
}
