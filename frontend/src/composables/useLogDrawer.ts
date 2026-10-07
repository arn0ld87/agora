/**
 * useLogDrawer — Open/Close-State + Hotkey-Handler fuer den globalen Log-Drawer
 * (Issue #132, Redesign PR 2 — Slice "Chrome bereinigen").
 *
 * Singleton-Ref (module-scope) sorgt dafuer, dass App.vue (LogDrawer-Mount +
 * Hotkey-Listener) und die Kopfzeilen-Icons in Topbar.vue
 * denselben reaktiven Zustand teilen, ohne Pinia-Overhead — analog
 * useCommandPalette.ts.
 *
 * Persistenz via localStorage, damit ein Reload den Drawer-Zustand haelt.
 */
import { computed, getCurrentScope, onBeforeUnmount, onMounted, onScopeDispose, ref, watch, type Ref } from 'vue'
import { buildLogsStreamUrl } from '../api/logs'
import { useOperatorAccess } from './useOperatorAccess'

const STORAGE_KEY = 'agora.ui.logDrawer.open'
const HEIGHT_KEY = 'agora.ui.logDrawer.height'

export const LOG_DRAWER_MIN_HEIGHT = 160
export const LOG_DRAWER_DEFAULT_HEIGHT = 320
/** Anteil der Fensterhöhe, den die Konsole höchstens einnehmen darf. */
const MAX_VIEWPORT_SHARE = 0.8
const WATCH_RETRY_MS = 30000

export function logDrawerMaxHeight(): number {
  const vh = typeof window !== 'undefined' ? window.innerHeight : 0
  return Math.max(LOG_DRAWER_MIN_HEIGHT, Math.floor(vh * MAX_VIEWPORT_SHARE) || 640)
}

export function clampLogDrawerHeight(px: number): number {
  if (!Number.isFinite(px)) return LOG_DRAWER_DEFAULT_HEIGHT
  return Math.min(logDrawerMaxHeight(), Math.max(LOG_DRAWER_MIN_HEIGHT, Math.round(px)))
}

function loadHeight(): number {
  try {
    const raw = localStorage.getItem(HEIGHT_KEY)
    if (raw === null) return LOG_DRAWER_DEFAULT_HEIGHT
    return clampLogDrawerHeight(Number(raw))
  } catch {
    return LOG_DRAWER_DEFAULT_HEIGHT
  }
}

function loadOpen(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

// Module-scope: Singleton-State damit alle Aufrufer denselben Ref teilen
const isOpen = ref(loadOpen())
const height = ref(loadHeight())
const unreadErrors = ref(0)

function persistOpen(): void {
  try {
    localStorage.setItem(STORAGE_KEY, String(isOpen.value))
  } catch {
    // localStorage nicht verfuegbar (Test ohne Mock, SSR) — ignorieren
  }
}

/** Hoehe der Konsole in px, begrenzt und in localStorage gemerkt. */
function setHeight(px: number): void {
  height.value = clampLogDrawerHeight(px)
  persistHeight()
}

/** Nur die Hoehe, ohne Strom-Beobachtung (fuer die Konsole selbst). */
export function useLogDrawerHeight() {
  return { height, setHeight }
}

function persistHeight(): void {
  try {
    localStorage.setItem(HEIGHT_KEY, String(height.value))
  } catch {
    // localStorage nicht verfuegbar — ignorieren
  }
}

// --- Fehlerzaehler bei geschlossener Konsole ---------------------------------
// Der Protokollstrom (SSE) laeuft in LogDrawer.vue nur bei offener Konsole.
// Damit der Zaehler ungelesener Fehler trotzdem stimmt, haelt dieses Modul bei
// geschlossener Konsole (nur Betreiber) EINE zusaetzliche SSE-Verbindung mit
// level=error offen: es kommen nur Fehlerzeilen an, gespeichert wird nur eine
// Zahl. Bei geoeffneter Konsole wird sie geschlossen (nie zwei Streams).
let watchSource: EventSource | null = null
let watchGeneration = 0
let watchRetryTimer: ReturnType<typeof setTimeout> | null = null
let watchSubscribers = 0

function stopErrorWatch(): void {
  watchGeneration++
  if (watchRetryTimer !== null) {
    clearTimeout(watchRetryTimer)
    watchRetryTimer = null
  }
  if (watchSource) {
    watchSource.close()
    watchSource = null
  }
}

async function startErrorWatch(): Promise<void> {
  stopErrorWatch()
  if (typeof EventSource === 'undefined') return
  const generation = watchGeneration
  try {
    const url = await buildLogsStreamUrl('error', null)
    if (generation !== watchGeneration) return
    const source = new EventSource(url)
    watchSource = source
    source.onmessage = (e: MessageEvent) => {
      try {
        const payload = JSON.parse(String(e.data)) as { line?: unknown }
        if (typeof payload?.line === 'string') unreadErrors.value += 1
      } catch {
        // Nicht-JSON-Frame ignorieren
      }
    }
    source.onerror = () => {
      // Der Browser verbindet bei transienten Fehlern selbst neu (mit
      // Last-Event-ID). Ist die Verbindung endgueltig zu (z. B. abgelaufenes
      // Ticket), nach Pause mit frischem Ticket neu aufbauen.
      if (source.readyState === 2 && generation === watchGeneration && watchRetryTimer === null) {
        watchRetryTimer = setTimeout(() => {
          watchRetryTimer = null
          if (generation === watchGeneration) void startErrorWatch()
        }, WATCH_RETRY_MS)
      }
    }
  } catch {
    // Ticket-/Verbindungsfehler: Zaehler bleibt, naechster Zustandswechsel versucht erneut
  }
}

// --- Protokollseite ---------------------------------------------------------
// Zeigt die Seite /activity/log den Protokollstrom, haelt sie ihn allein: die
// Konsole bleibt dann unsichtbar (ihr Strom endet) und der Fehlerzaehler
// oeffnet keine zweite Verbindung. So gibt es nie zwei Streams gleichzeitig.
const pageClaims = ref(0)

/** Aus einer Komponente: meldet fuer ihre Lebenszeit, dass die Seite den Strom haelt. */
export function useLogStreamPageClaim(): void {
  onMounted(() => { pageClaims.value++ })
  onBeforeUnmount(() => { pageClaims.value = Math.max(0, pageClaims.value - 1) })
}

export function useLogDrawer() {
  // Logs sind Betreiber-Zustand (operator_only, #1617): für Supabase-Nutzer
  // weder Knopf noch Hotkey noch Drawer.
  const available = useOperatorAccess()
  const visible = computed(() => isOpen.value && available.value && pageClaims.value === 0)

  // Nur aus einem Effekt-Scope (Komponente): Strom folgt "Betreiber und
  // geschlossen". Mehrere Aufrufer stimmen im Ergebnis ueberein; der letzte
  // abgemeldete Aufrufer beendet den Strom.
  if (getCurrentScope()) {
    watchSubscribers++
    watch(
      () => available.value && !isOpen.value && pageClaims.value === 0,
      (shouldWatch) => {
        if (shouldWatch) {
          if (!watchSource && watchRetryTimer === null) void startErrorWatch()
        } else {
          stopErrorWatch()
        }
      },
      { immediate: true },
    )
    onScopeDispose(() => {
      watchSubscribers--
      if (watchSubscribers <= 0) {
        watchSubscribers = 0
        stopErrorWatch()
      }
    })
  }

  function open(): void {
    if (!available.value) return
    isOpen.value = true
    unreadErrors.value = 0
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
    height,
    setHeight,
    unreadErrors: unreadErrors as Readonly<Ref<number>>,
  }
}
