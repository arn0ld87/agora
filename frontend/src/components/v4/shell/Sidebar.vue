<template>
  <aside class="sidebar" :class="{ 'sidebar--collapsed': collapsed }">
    <!-- Brand header -->
    <div class="sidebar__brand">
      <svg width="26" height="26" viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <defs>
          <linearGradient id="sidebar-glyph-grad" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
            <stop offset="0" stop-color="#0A84FF"/>
            <stop offset="1" stop-color="#0040A0"/>
          </linearGradient>
        </defs>
        <rect x="1" y="1" width="30" height="30" rx="9" fill="url(#sidebar-glyph-grad)"/>
        <path d="M9 22.5 L16 9.5 L23 22.5" stroke="white" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
        <line x1="11.8" y1="17.5" x2="20.2" y2="17.5" stroke="white" stroke-width="2.4" stroke-linecap="round"/>
        <circle cx="16" cy="9.5" r="1.6" fill="white"/>
      </svg>
      <span v-if="!collapsed" class="sidebar__wordmark">Agora</span>
    </div>

    <!-- Nav body -->
    <nav class="sidebar__body" aria-label="Hauptnavigation">
      <!-- Workspace items -->
      <template v-for="item in navWorkspace" :key="item.id">
        <SidebarItem
          :icon="item.icon"
          :label="item.label"
          :to="item.to"
          :active="active === item.id"
        />
      </template>

      <!-- Settings group -->
      <SidebarGroup
        label="Settings"
        icon="settings"
        :open="settingsOpen"
        :active="active === 'settings' && !settingsOpen"
        @update:open="onSettingsGroupToggle"
      >
        <template v-for="sub in navSettings" :key="sub.id">
          <RouterLink
            :to="sub.to"
            class="sidebar-sub-item"
            :class="{ 'sidebar-sub-item--active': subActive === sub.id }"
          >
            {{ sub.label }}
          </RouterLink>
        </template>
      </SidebarGroup>
    </nav>

    <!-- Footer collapse toggle -->
    <div class="sidebar__footer" @click="emit('collapse-toggle')">
      <Icon :name="collapsed ? 'arrowL' : 'arrowL'" :size="14" :stroke="1.6" />
      <span v-if="!collapsed" class="sidebar__footer-label">Collapse</span>
    </div>
  </aside>
</template>

<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'
import SidebarItem from './SidebarItem.vue'
import SidebarGroup from './SidebarGroup.vue'
import Icon from './Icon.vue'

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
    active?: string
    subActive?: string
    settingsOpen?: boolean
    collapsed?: boolean
  }>(),
  {
    active: '',
    subActive: '',
    settingsOpen: false,
    collapsed: false,
  },
)

const emit = defineEmits<{
  'update:settingsOpen': [value: boolean]
  'collapse-toggle': []
}>()

function onSettingsGroupToggle(value: boolean): void {
  emit('update:settingsOpen', value)
}

const navWorkspace: NavItem[] = [
  { id: 'dashboard', icon: 'home',   label: 'Dashboard',  to: { name: 'Dashboard' } },
  { id: 'runs',      icon: 'branch', label: 'Runs',       to: { name: 'Runs' } },
  { id: 'projects',  icon: 'folder', label: 'Projects',   to: { path: '#projects' } },
  { id: 'datasets',  icon: 'layers', label: 'Datasets',   to: { path: '#datasets' } },
  { id: 'templates', icon: 'doc',    label: 'Templates',  to: { path: '#templates' } },
  { id: 'monitoring',icon: 'spark',  label: 'Monitoring', to: { path: '#monitoring' } },
]

const navSettings: NavSettingsItem[] = [
  { id: 'general',       label: 'General',       to: { name: 'SettingsGeneral' } },
  { id: 'integrations',  label: 'Integrations',  to: { name: 'SettingsIntegrations' } },
  { id: 'users-teams',   label: 'Users & Teams', to: { name: 'SettingsUsersTeams' } },
  { id: 'api-keys',      label: 'API Keys',      to: { name: 'SettingsApiKeys' } },
  { id: 'llm-providers', label: 'LLM Providers', to: { name: 'SettingsLlmProviders' } },
  { id: 'llm-routing',   label: 'LLM Routing',   to: { name: 'SettingsLlmRouting' } },
  { id: 'audit',         label: 'Audit Logs',    to: { name: 'SettingsAuditLogs' } },
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
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
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
