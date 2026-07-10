<template>
  <div class="app-shell" :class="{ 'app-shell--inspector-open': shellStore.inspectorOpen }">
    <!-- Mobile Backdrop -->
    <div
      v-if="shellStore.mobileNavOpen"
      class="app-shell__backdrop"
      aria-hidden="true"
      @click="shellStore.closeMobileNav()"
    />

    <!-- Sidebar (spans both rows on Desktop; Off-Canvas on Mobile) -->
    <div
      class="app-shell__sidebar"
      :class="{ 'app-shell__sidebar--mobile-open': shellStore.mobileNavOpen }"
    >
      <slot name="sidebar">
        <Sidebar
          :active="activeRoute"
          :sub-active="activeSubRoute"
          :settings-open="shellStore.settingsGroupOpen"
          :collapsed="shellStore.sidebarCollapsed"
          @update:settings-open="shellStore.settingsGroupOpen = $event"
          @collapse-toggle="shellStore.toggleSidebar"
        />
      </slot>
    </div>

    <!-- Topbar -->
    <div class="app-shell__topbar">
      <slot name="topbar">
        <Topbar :breadcrumbs="breadcrumbs" :notification-badge="notificationBadge" />
      </slot>
    </div>

    <!-- Main content -->
    <main class="app-shell__main">
      <slot />
    </main>

    <!-- Inspector (optional, default closed) -->
    <div v-if="shellStore.inspectorOpen" class="app-shell__inspector">
      <slot name="inspector" />
    </div>

    <!-- Command-Palette (global, rendered einmalig in Shell) -->
    <CommandPalette v-if="isPaletteOpen" />
  </div>
</template>

<script setup lang="ts">
import { computed, watch, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useShellStore } from '@/stores/shell'
import { useCommandPalette } from '@/composables/useCommandPalette'
import { useCommandsStore } from '@/stores/commandsStore'
import Sidebar from './Sidebar.vue'
import Topbar from './Topbar.vue'
import type { BreadcrumbItem } from './Breadcrumbs.vue'

// Async-Import: CommandPalette in eigenem Chunk → kein AppShell-Bundle-Overhead
const CommandPalette = defineAsyncComponent(() => import('./CommandPalette.vue'))

const props = withDefaults(
  defineProps<{
    breadcrumbs?: BreadcrumbItem[]
    notificationBadge?: number
  }>(),
  {
    breadcrumbs: () => [],
    notificationBadge: 0,
  },
)

const shellStore = useShellStore()
const route = useRoute()
const router = useRouter()
const { isOpen: isPaletteOpen, toggle: togglePalette } = useCommandPalette()
const commandsStore = useCommandsStore()

function onKeyDown(e: KeyboardEvent): void {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    togglePalette()
  }
  if (e.key === 'Escape' && shellStore.mobileNavOpen) {
    shellStore.closeMobileNav()
  }
}

// Resize-Listener: Wenn auf Desktop-Breite gewechselt wird während Drawer offen ist,
// Nav schliessen damit der Scroll-Lock (via Watcher unten) aufgehoben wird.
function onResize(): void {
  if (window.innerWidth >= 768 && shellStore.mobileNavOpen) {
    shellStore.closeMobileNav()
  }
}

// Body-Scroll-Lock wenn Mobile-Nav offen
watch(
  () => shellStore.mobileNavOpen,
  (open) => {
    if (typeof document !== 'undefined') {
      document.body.style.overflow = open ? 'hidden' : ''
    }
  },
)

onMounted(() => {
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('resize', onResize)
  // Dynamische Commands (laufende Sims + Recent Reports) einmalig verdrahten.
  // bindDynamicCommands ist idempotent — doppelter Aufruf ist sicher.
  commandsStore.bindDynamicCommands(router)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('resize', onResize)
  commandsStore.unbindDynamicCommands()
  // Scroll-Lock immer freigeben
  if (typeof document !== 'undefined') {
    document.body.style.overflow = ''
  }
})

// Derive active route name for sidebar item highlighting
const activeRoute = computed<string>(() => {
  const name = route.name
  if (!name) return ''
  const n = String(name).toLowerCase()
  if (n === 'home' || n === 'dashboard') return 'dashboard'
  if (n === 'runs' || n === 'rundetail' || n === 'runsappshell' || n === 'rundetailappshell') return 'runs'
  if (n === 'settings' || n.startsWith('settings')) return 'settings'
  return n
})

// Derive active settings sub-tab from query param or route name
const activeSubRoute = computed<string>(() => {
  const tab = route.query['tab']
  if (typeof tab === 'string') return tab
  // Named Settings-sub-routes: SettingsLlmRouting → 'llm-routing'
  const routeName = String(route.name ?? '')
  if (routeName.startsWith('Settings') && routeName !== 'Settings') {
    // e.g. 'SettingsLlmRouting' → 'llm-routing'
    return routeName
      .replace(/^Settings/, '')
      .replace(/([A-Z])/g, (m, c, i) => (i === 0 ? c.toLowerCase() : '-' + c.toLowerCase()))
  }
  return ''
})
</script>

<style scoped>
.app-shell {
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: 64px 1fr;
  background: var(--surface-canvas, #f5f5f7);
  overflow: hidden;
}

.app-shell--inspector-open {
  grid-template-columns: auto 1fr 360px;
}

.app-shell__sidebar {
  grid-row: 1 / 3;
  grid-column: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.app-shell__topbar {
  grid-row: 1;
  grid-column: 2;
  min-width: 0;
}

.app-shell--inspector-open .app-shell__topbar {
  grid-column: 2 / 3;
}

.app-shell__main {
  grid-row: 2;
  grid-column: 2;
  overflow: auto;
  padding: 28px 36px;
  min-width: 0;
}

.app-shell--inspector-open .app-shell__main {
  grid-column: 2 / 3;
}

.app-shell__inspector {
  grid-row: 1 / 3;
  grid-column: 3;
  width: 360px;
  border-left: 1px solid var(--hairline);
  background: var(--surface-base, #fff);
  overflow: auto;
}

/* Backdrop: nur auf Mobile sichtbar */
.app-shell__backdrop {
  display: none;
}

/* ── Mobile (< 768 px) ──────────────────────────────────────── */
@media (max-width: 768px) {
  .app-shell {
    grid-template-columns: 1fr;
    grid-template-rows: 56px 1fr;
  }

  /* Inspector als Full-Screen-Overlay auf Mobile */
  .app-shell--inspector-open {
    grid-template-columns: 1fr;
  }

  .app-shell__sidebar {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    z-index: 50;
    grid-row: unset;
    grid-column: unset;
    transform: translateX(-100%);
    transition: transform 200ms ease;
    /* Erzwingt volle Sidebar-Breite im Mobile-Drawer, auch wenn Desktop-Collapsed-State
       (56px) aktiv ist — sonst sind Labels unsichtbar und der Drawer wirkt kaputt. */
    width: 280px !important;
  }

  .app-shell__sidebar--mobile-open {
    transform: translateX(0);
  }

  .app-shell__topbar {
    grid-row: 1;
    grid-column: 1;
  }

  .app-shell--inspector-open .app-shell__topbar {
    grid-column: 1;
  }

  .app-shell__main {
    grid-row: 2;
    grid-column: 1;
    padding: 16px;
  }

  .app-shell--inspector-open .app-shell__main {
    grid-column: 1;
  }

  /* Inspector als Full-Screen-Overlay */
  .app-shell__inspector {
    position: fixed;
    inset: 0;
    z-index: 60;
    width: 100%;
    border-left: none;
    grid-row: unset;
    grid-column: unset;
  }

  /* Backdrop aktiv */
  .app-shell__backdrop {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 40;
    background: rgba(0, 0, 0, 0.45);
  }
}
</style>
