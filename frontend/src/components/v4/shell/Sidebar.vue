<template>
  <aside class="sidebar" :class="{ 'sidebar--collapsed': collapsed }">
    <!-- Brand header -->
    <div class="sidebar__brand">
      <AgoraBrand mode="glyph" :height="28" alt="Agora" />
      <span v-if="!collapsed" class="sidebar__wordmark">Agora</span>
    </div>

    <!-- Nav body -->
    <nav class="sidebar__body" aria-label="Hauptnavigation">
      <!-- Workspace items (IA-Matrix Slice 7.3: nur wire-Ziele) -->
      <template v-for="item in navWorkspace" :key="item.id">
        <SidebarItem
          :icon="item.icon"
          :label="item.label"
          :to="item.to"
          @click="handleNavClick"
        />
      </template>

      <!-- Settings group (IA-Matrix: nur wire-Sub-Items) -->
      <SidebarGroup
        group-key="settings"
        :label="t('sidebar.settings.label')"
        icon="settings"
        :active-route-names="settingsRouteNames"
      >
        <template v-for="sub in navSettings" :key="sub.id">
          <RouterLink
            :to="sub.to"
            class="sidebar-sub-item"
            active-class="sidebar-sub-item--active"
            exact-active-class="sidebar-sub-item--active"
            @click="handleNavClick"
          >
            {{ sub.label }}
          </RouterLink>
        </template>
      </SidebarGroup>
    </nav>

    <!-- Footer collapse toggle -->
    <button
      type="button"
      class="sidebar__footer"
      :aria-label="collapsed ? t('sidebar.footer.expand') : t('sidebar.footer.collapse')"
      @click="emit('collapse-toggle')"
    >
      <Icon :name="collapsed ? 'arrowL' : 'arrowL'" :size="14" :stroke="1.6" />
      <span v-if="!collapsed" class="sidebar__footer-label">{{ t('sidebar.footer.collapse') }}</span>
    </button>
  </aside>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { RouteLocationRaw } from 'vue-router'
import SidebarItem from './SidebarItem.vue'
import SidebarGroup from './SidebarGroup.vue'
import Icon from './Icon.vue'
import AgoraBrand from '../../brand/AgoraBrand.vue'
import { useShellStore } from '@/stores/shell'
import { MOBILE_MEDIA_QUERY } from '@/constants/breakpoints'

const { t } = useI18n()
const shellStore = useShellStore()

function handleNavClick(): void {
  // MOBILE_MEDIA_QUERY (SSoT, Slice 7.3.2) matcht "< MOBILE_BREAKPOINT_PX" —
  // konsistent mit AppShell.vue's Resize-Handler (window.innerWidth >= 768).
  if (window.matchMedia(MOBILE_MEDIA_QUERY).matches) {
    shellStore.closeMobileNav()
  }
}

interface NavItem {
  id: string
  icon: string
  label: string
  to: RouteLocationRaw
}

interface NavSettingsItem {
  id: string
  label: string
  to: RouteLocationRaw
}

const props = withDefaults(
  defineProps<{
    collapsed?: boolean
  }>(),
  {
    collapsed: false,
  },
)

const emit = defineEmits<{
  'collapse-toggle': []
}>()

/** Alle Route-Namen, bei denen die Settings-Gruppe als aktiv gilt und auto-oeffnet.
 *  IA-Matrix Slice 7.3: SettingsAuditLogs und SettingsLlmRouting sind nicht in der Sidebar,
 *  muessen hier aber gelistet bleiben, damit ein Aufruf der Hidden-Route (z.B. via
 *  CommandPalette oder Deep-Link) die Gruppe trotzdem auto-oeffnet. */
const settingsRouteNames = [
  'Settings',
  'SettingsGeneral',
  'SettingsIntegrations',
  'SettingsProfile',
  'SettingsApiKeys',
  'SettingsAuditLogs',
  'SettingsLlmRouting',
  'SettingsLlmProviders',
  'SettingsEmbedding',
]

/** IA-Matrix Slice 7.3 — nur wire-Ziele in der Sidebar.
 *  Projekte/Datensaetze/Vorlagen/Monitoring: hide (MVP Slice 8+).
 *  Audit Logs + LLM-Routing: hide. */
const navWorkspace = [
  { id: 'dashboard',  icon: 'home',   label: t('sidebar.nav.dashboard'),  to: { name: 'Dashboard' } },
  { id: 'runs',       icon: 'branch', label: t('sidebar.nav.runs'),       to: { name: 'Runs' } },
] satisfies NavItem[]

/** IA-Matrix: nur wire-Settings-Sub-Items. */
const navSettings: NavSettingsItem[] = [
  { id: 'general',       label: t('sidebar.settings.general'),       to: { name: 'SettingsGeneral' } },
  { id: 'integrations',  label: t('sidebar.settings.integrations'),  to: { name: 'SettingsIntegrations' } },
  { id: 'profile',       label: t('sidebar.settings.profile'),       to: { name: 'SettingsProfile' } },
  { id: 'api-keys',      label: t('sidebar.settings.apiKeys'),       to: { name: 'SettingsApiKeys' } },
  { id: 'llm-providers', label: t('sidebar.settings.llmProviders'),  to: { name: 'SettingsLlmProviders' } },
  { id: 'embedding',     label: t('sidebar.settings.embedding'),     to: { name: 'SettingsEmbedding' } },
]
</script>

<style scoped>
.sidebar {
  width: 220px;
  background: var(--surface-base, #fff);
  border-right: 1px solid var(--hairline);
  display: flex;
  flex-direction: column;
  height: 100%;
  flex-shrink: 0;
  transition: width var(--v4-state-motion-duration-base) var(--v4-state-motion-ease);
  overflow: hidden;
}

@media (prefers-reduced-motion: reduce) {
  .sidebar {
    transition: none;
  }
}

.sidebar--collapsed {
  width: 56px;
}

.sidebar__brand {
  height: 64px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 18px;
  flex-shrink: 0;
}

.sidebar__wordmark {
  font-size: 19px;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--text-primary);
  font-family: var(--font-sans);
  white-space: nowrap;
}

.sidebar__body {
  padding: 8px var(--sidebar-item-px, 10px);
  display: flex;
  flex-direction: column;
  gap: var(--sidebar-group-gap, 2px);
  flex: 1;
  overflow-y: auto;
}

.sidebar__footer {
  width: 100%;
  padding: 10px 18px;
  border: 0;
  border-top: 1px solid var(--separator, var(--hairline));
  border-radius: 0;
  background: transparent;
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  flex-shrink: 0;
  user-select: none;
  transition: color 100ms ease;
}

.sidebar__footer:hover {
  color: var(--text-primary);
}

/* Die Unterpunkte der Einstellungen-Gruppe hatten keinen Fokusring —
   mit der Tastatur war nicht sichtbar, wo man steht. */
.sidebar-sub-item:focus-visible {
  outline: var(--v4-state-focus-ring-width) solid var(--v4-state-focus-ring);
  outline-offset: var(--v4-state-focus-ring-offset);
}

.sidebar__footer:focus-visible {
  outline: 2px solid var(--accent, #2563eb);
  outline-offset: -2px;
}

.sidebar__footer-label {
  white-space: nowrap;
}
</style>