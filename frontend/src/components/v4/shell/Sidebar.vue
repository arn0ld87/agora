<template>
  <aside class="sidebar" :class="{ 'sidebar--collapsed': collapsed }">
    <!-- Brand header -->
    <div class="sidebar__brand">
      <AgoraBrand mode="glyph" :height="28" alt="Agora" />
      <span v-if="!collapsed" class="sidebar__wordmark">Agora</span>
    </div>

    <!-- Nav body -->
    <nav class="sidebar__body" aria-label="Hauptnavigation">
      <!-- Workspace items -->
      <template v-for="item in navWorkspace" :key="item.id">
        <SidebarItem
          :icon="item.icon"
          :label="item.label"
          :to="item.disabled ? undefined : item.to"
          :disabled="item.disabled"
          :tooltip="item.disabled ? t('sidebar.disabledTooltip') : undefined"
          @click="handleNavClick"
        />
      </template>

      <!-- Settings group -->
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
    <div class="sidebar__footer" @click="emit('collapse-toggle')">
      <Icon :name="collapsed ? 'arrowL' : 'arrowL'" :size="14" :stroke="1.6" />
      <span v-if="!collapsed" class="sidebar__footer-label">{{ t('sidebar.footer.collapse') }}</span>
    </div>
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

const { t } = useI18n()
const shellStore = useShellStore()

function handleNavClick(): void {
  if (window.innerWidth < 768) {
    shellStore.closeMobileNav()
  }
}

interface NavItem {
  id: string
  icon: string
  label: string
  to: RouteLocationRaw
  /** Wenn true: kein Router-Push, aria-disabled, gedimmtes Styling, Tooltip. */
  disabled?: boolean
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

/** Alle Route-Namen, bei denen die Settings-Gruppe als aktiv gilt und auto-öffnet. */
const settingsRouteNames = [
  'Settings',
  'SettingsGeneral',
  'SettingsIntegrations',
  'SettingsUsersTeams',
  'SettingsApiKeys',
  'SettingsAuditLogs',
  'SettingsLlmRouting',
  'SettingsLlmProviders',
]

const navWorkspace = [
  { id: 'dashboard',  icon: 'home',   label: t('sidebar.nav.dashboard'),  to: { name: 'Dashboard' } },
  { id: 'runs',       icon: 'branch', label: t('sidebar.nav.runs'),       to: { name: 'Runs' } },
  { id: 'projects',   icon: 'folder', label: t('sidebar.nav.projects'),   to: { path: '#projects' },  disabled: true },
  { id: 'datasets',   icon: 'layers', label: t('sidebar.nav.datasets'),   to: { path: '#datasets' },  disabled: true },
  { id: 'templates',  icon: 'doc',    label: t('sidebar.nav.templates'),  to: { path: '#templates' }, disabled: true },
  { id: 'monitoring', icon: 'spark',  label: t('sidebar.nav.monitoring'), to: { path: '#monitoring' },disabled: true },
] satisfies NavItem[]

const navSettings: NavSettingsItem[] = [
  { id: 'general',       label: t('sidebar.settings.general'),       to: { name: 'SettingsGeneral' } },
  { id: 'integrations',  label: t('sidebar.settings.integrations'),  to: { name: 'SettingsIntegrations' } },
  { id: 'users-teams',   label: t('sidebar.settings.usersTeams'),    to: { name: 'SettingsUsersTeams' } },
  { id: 'api-keys',      label: t('sidebar.settings.apiKeys'),       to: { name: 'SettingsApiKeys' } },
  { id: 'audit',         label: t('sidebar.settings.auditLogs'),     to: { name: 'SettingsAuditLogs' } },
  { id: 'llm-providers', label: t('sidebar.settings.llmProviders'),  to: { name: 'SettingsLlmProviders' } },
  { id: 'llm-routing',   label: t('sidebar.settings.llmRouting'),    to: { name: 'SettingsLlmRouting' } },
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
  transition: width 200ms ease;
  overflow: hidden;
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
  padding: 10px 18px;
  border-top: 1px solid var(--separator, var(--hairline));
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  flex-shrink: 0;
  user-select: none;
  transition: color 100ms ease;
}

.sidebar__footer:hover {
  color: var(--text-primary);
}

.sidebar__footer-label {
  white-space: nowrap;
}
</style>
