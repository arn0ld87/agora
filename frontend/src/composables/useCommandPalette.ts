/**
 * useCommandPalette — Open/Close-State + Recent-Stack
 *
 * Singleton-Refs (module-scope) sorgen dafuer, dass AppShell-Keydown-Listener
 * und CommandPalette.vue denselben reaktiven Zustand teilen, ohne Pinia-Overhead.
 *
 * Recent-Stack: max 8 Eintraege, deduped, persistent via localStorage.
 */
import { ref } from 'vue'

const STORAGE_KEY = 'agora.cmdk.recent'
const RECENT_MAX = 8

function hydrateRecent(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as string[]) : []
  } catch {
    return []
  }
}

// Module-scope: Singleton-State damit alle Aufrufer denselben Ref teilen
const isOpen = ref(false)
const query = ref('')
const recent = ref<string[]>(hydrateRecent())

export function useCommandPalette() {
  function open(): void {
    isOpen.value = true
    query.value = ''
  }

  function close(): void {
    isOpen.value = false
  }

  function toggle(): void {
    if (isOpen.value) {
      close()
    } else {
      open()
    }
  }

  function pushRecent(commandId: string): void {
    const without = recent.value.filter((id) => id !== commandId)
    recent.value = [commandId, ...without].slice(0, RECENT_MAX)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(recent.value))
    } catch {
      // localStorage nicht verfuegbar (Test ohne Mock, SSR) — ignorieren
    }
  }

  function clearRecent(): void {
    recent.value = []
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      // ignorieren
    }
  }

  return {
    isOpen,
    query,
    recent,
    open,
    close,
    toggle,
    pushRecent,
    clearRecent,
  }
}
