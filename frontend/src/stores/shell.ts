import { ref, watch } from 'vue'
import { defineStore } from 'pinia'

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
