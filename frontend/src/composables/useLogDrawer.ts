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
import { computed, ref } from 'vue'
import { useAuthStore } from '../store/auth'

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
  // Logs sind Betreiber-Zustand (operator_only, #1617): für Supabase-Nutzer
  // weder Knopf noch Hotkey noch Drawer. Ohne aktives Pinia (isolierte
  // Tests) bleibt es beim bisherigen Verhalten.
  let auth: ReturnType<typeof useAuthStore> | null = null
  try {
    auth = useAuthStore()
  } catch {
    auth = null
  }
  const available = computed(() => auth?.operatorAccess ?? true)
  const visible = computed(() => isOpen.value && available.value)

  function open(): void {
    if (!available.value) return
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
      if (!available.value) return
      e.preventDefault()
      toggle()
    }
  }

  return {
    isOpen,
    available,
    visible,
    open,
    close,
    toggle,
    handleHotkey,
  }
}
