import { ref } from 'vue'

/**
 * Feature-Flag der Neuhuelle (Block B3, PLAN.md Abschnitt 2).
 *
 * Aufgeloest an GENAU EINER Stelle: der Wurzel-Route in router/index.ts.
 * Kein Flag tief in Komponenten — sonst wird er nie wieder entfernbar.
 * Der Flag faellt am Ende von Block B3 zusammen mit AppShell/Sidebar/
 * Topbar und den Legacy-Views.
 *
 * Aufloesungsreihenfolge:
 *   1. localStorage["agora.shell"]  — Laufzeit-Override im Browser
 *   2. VITE_AGORA_SHELL             — Build-Default
 *   3. "classic"                    — bis die Dossier-Huelle traegt
 */
export type ShellVariant = 'classic' | 'dossier'

const STORAGE_KEY = 'agora.shell'

function resolveVariant(): ShellVariant {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'classic' || stored === 'dossier') return stored
  } catch {
    /* localStorage kann in Testumgebungen fehlen — Build-Default gilt. */
  }
  const env = (import.meta.env.VITE_AGORA_SHELL as string | undefined) ?? ''
  if (env === 'dossier' || env === 'classic') return env
  return 'classic'
}

const variant = ref<ShellVariant>(resolveVariant())

export function useShellVariant() {
  function setVariant(next: ShellVariant): void {
    variant.value = next
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* ohne Persistenz gilt der Wechsel nur fuer diese Session */
    }
  }
  return { variant, setVariant }
}
