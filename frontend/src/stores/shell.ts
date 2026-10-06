import { ref, watch } from 'vue'
import { defineStore } from 'pinia'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import type { ShelfObject, ShelfSource } from '@/types/shelf'

/** Geladener Ablage-Stand samt der Quellen, die dabei fehlten. */
export interface ShelfSnapshot {
  objects: ShelfObject[]
  unavailable: ShelfSource[]
}

const KEYS = {
  sidebarCollapsed: 'agora.v4.shell.sidebarCollapsed',
  settingsGroupOpen: 'agora.v4.shell.settingsGroupOpen',
  inspectorOpen: 'agora.v4.shell.inspectorOpen',
} as const

function readBool(key: string, fallback: boolean): boolean {
  try {
    const raw = localStorage.getItem(key)
    if (raw === null) return fallback
    return raw === 'true'
  } catch {
    return fallback
  }
}

function writeBool(key: string, value: boolean): void {
  try {
    localStorage.setItem(key, value ? 'true' : 'false')
  } catch {
    // localStorage nicht verfuegbar (z.B. SSR / Test ohne Mock) — ignorieren
  }
}

export const useShellStore = defineStore('shell', () => {
  const sidebarCollapsed = ref<boolean>(readBool(KEYS.sidebarCollapsed, false))
  const settingsGroupOpen = ref<boolean>(readBool(KEYS.settingsGroupOpen, true))
  const inspectorOpen = ref<boolean>(readBool(KEYS.inspectorOpen, false))

  // Mobile-Nav — kein localStorage, soll bei jedem Reload geschlossen sein
  const mobileNavOpen = ref<boolean>(false)

  // Brotkrumen der aktuellen Ansicht (#1795): gesetzt ueber
  // useShellBreadcrumbs, gelesen von AppShell. Fluechtig, nie persistiert.
  const breadcrumbs = ref<BreadcrumbItem[]>([])

  // Laufende Ablage-Objekte fuer den Aktivitaets-Indikator in der Kopfleiste
  // (#1795): ShelfView meldet sie, ShelfActivity liest sie. Fluechtig.
  const activeObjects = ref<ShelfObject[]>([])

  // Letzter geladener Stand der Ablage (#1795): ShelfView und die Zaehler der
  // Seitenleiste schreiben ihn, die Seitenleiste liest ihn. Ein gemeinsamer
  // Stand statt zweier Ladevorgaenge. null = noch nie geladen. Fluechtig.
  const shelfSnapshot = ref<ShelfSnapshot | null>(null)

  watch(sidebarCollapsed, (v) => writeBool(KEYS.sidebarCollapsed, v))
  watch(settingsGroupOpen, (v) => writeBool(KEYS.settingsGroupOpen, v))
  watch(inspectorOpen, (v) => writeBool(KEYS.inspectorOpen, v))

  function toggleSidebar(): void {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function toggleSettingsGroup(): void {
    settingsGroupOpen.value = !settingsGroupOpen.value
  }

  function toggleInspector(): void {
    inspectorOpen.value = !inspectorOpen.value
  }

  function openInspector(): void {
    inspectorOpen.value = true
  }

  function closeInspector(): void {
    inspectorOpen.value = false
  }

  function openMobileNav(): void {
    mobileNavOpen.value = true
  }

  function closeMobileNav(): void {
    mobileNavOpen.value = false
  }

  function toggleMobileNav(): void {
    mobileNavOpen.value = !mobileNavOpen.value
  }

  return {
    sidebarCollapsed,
    settingsGroupOpen,
    inspectorOpen,
    mobileNavOpen,
    breadcrumbs,
    activeObjects,
    shelfSnapshot,
    toggleSidebar,
    toggleSettingsGroup,
    toggleInspector,
    openInspector,
    closeInspector,
    openMobileNav,
    closeMobileNav,
    toggleMobileNav,
  }
})
