<template>
  <div class="app-shell" :class="{ 'app-shell--inspector-open': shellStore.inspectorOpen }">
    <!-- Sidebar (spans both rows) -->
    <div class="app-shell__sidebar">
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
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useShellStore } from '@/stores/shell'
import Sidebar from './Sidebar.vue'
import Topbar from './Topbar.vue'
import type { BreadcrumbItem } from './Breadcrumbs.vue'

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

// Derive active route name for sidebar item highlighting
const activeRoute = computed<string>(() => {
  const name = route.name
  if (!name) return ''
  const n = String(name).toLowerCase()
  if (n === 'home') return 'dashboard'
  if (n === 'runs' || n === 'rundetail') return 'runs'
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
</style>
