/**
 * useLogDrawer — Open/Close-State + Hotkey-Handler fuer den globalen Log-Drawer
 * (Issue #132, Redesign PR 2 — Slice "Chrome bereinigen").
 *
 * Singleton-Ref (module-scope) sorgt dafuer, dass App.vue (LogDrawer-Mount +
 * Hotkey-Listener) und die Kopfzeilen-Icons in Topbar.vue/ShellRoot.vue
 * denselben reaktiven Zustand teilen, ohne Pinia-Overhead — analog
 * useCommandPalette.ts.
 *
 * Persistenz via localStorage, damit ein Reload den Drawer-Zustand haelt.
 */
import { ref } from 'vue'

const STORAGE_KEY = 'agora.ui.logDrawer.open'

function loadOpen(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

// Module-scope: Singleton-State damit alle Aufrufer denselben Ref teilen
const isOpen = ref(loadOpen())

function persistOpen(): void {
  try {
    localStorage.setItem(STORAGE_KEY, String(isOpen.value))
  } catch {
    // localStorage nicht verfuegbar (Test ohne Mock, SSR) — ignorieren
  }
}

export function useLogDrawer() {
  function open(): void {
    isOpen.value = true
    persistOpen()
  }

  function close(): void {
    isOpen.value = false
    persistOpen()
  }

  function toggle(): void {
    if (isOpen.value) {
      close()
    } else {
      open()
    }
  }

  /** Ctrl/Cmd+Shift+L — Registrierung des window-Listeners bleibt bei App.vue
   *  (einziger dauerhafter Mount-Punkt), damit der Listener nur einmal
   *  angehaengt wird. */
  function handleHotkey(e: KeyboardEvent): void {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'L' || e.key === 'l')) {
      e.preventDefault()
      toggle()
    }
  }

  return {
    isOpen,
    open,
    close,
    toggle,
    handleHotkey,
  }
}
