<script setup lang="ts">
import { ref } from 'vue'
import Icon from './Icon.vue'
import ModelPill from './ModelPill.vue'

const props = withDefaults(
  defineProps<{
    active?: string
    crumbs?: string[]
    modelProvider?: string
    modelName?: string
    modelLabel?: string
    padless?: boolean
  }>(),
  {
    active: 'dashboard',
    crumbs: () => [],
    modelProvider: 'ollama',
    modelName: 'glm-5.1',
    modelLabel: 'Workspace',
    padless: false,
  },
)

const emit = defineEmits<{ (e: 'nav', key: string): void }>()

const settingsOpen = ref(false)

const workspaceItems = [
  { key: 'dashboard', icon: 'dashboard', label: 'Dashboard' },
  { key: 'runs', icon: 'runs', label: 'Runs', count: '34', live: true },
  { key: 'projects', icon: 'projects', label: 'Projekte', count: '12' },
  { key: 'datasets', icon: 'datasets', label: 'Datensätze' },
  { key: 'templates', icon: 'templates', label: 'Vorlagen' },
]
</script>

<template>
  <div class="a26-shell">
    <!-- Rail -->
    <aside class="a26-rail">
      <div class="a26-rail-brand">
        <div class="a26-rail-mark" />
        <div class="a26-rail-brand-text">
          <span class="name">Agora</span>
          <span class="meta">Workbench · v4</span>
        </div>
      </div>

      <div class="a26-rail-section">Arbeitsbereich</div>
      <button
        v-for="it in workspaceItems"
        :key="it.key"
        type="button"
        class="a26-nav-row"
        :class="{ 'is-active': active === it.key }"
        @click="emit('nav', it.key)"
      >
        <span class="ico"><Icon :name="it.icon" /></span>
        <span>{{ it.label }}</span>
        <span v-if="it.count" class="count" :class="{ live: it.live }">{{ it.count }}</span>
      </button>

      <div class="a26-rail-section">System</div>
      <button
        type="button"
        class="a26-nav-row"
        :class="{ 'is-active': active === 'monitoring' }"
        @click="emit('nav', 'monitoring')"
      >
        <span class="ico"><Icon name="monitoring" /></span>
        <span>Monitoring</span>
      </button>
      <button
        type="button"
        class="a26-nav-row"
        :class="{ 'is-active': active === 'settings' }"
        style="padding-right: 8px"
        @click="settingsOpen = !settingsOpen"
      >
        <span class="ico"><Icon name="settings" /></span>
        <span>Einstellungen</span>
        <span
          style="margin-left: auto; color: var(--a26-ink-3); transition: transform 200ms"
          :style="{ transform: settingsOpen ? 'rotate(90deg)' : 'none' }"
        ><Icon name="chevron" /></span>
      </button>
      <div v-if="settingsOpen" class="a26-nav-sub">
        <button class="a26-nav-row" type="button"><span>Allgemein</span></button>
        <button class="a26-nav-row" type="button"><span>Integrationen</span></button>
        <button class="a26-nav-row" type="button"><span>Nutzer & Teams</span></button>
        <button class="a26-nav-row" type="button"><span>API-Schlüssel</span></button>
        <button class="a26-nav-row" type="button"><span>Audit-Logs</span></button>
        <button class="a26-nav-row" type="button"><span>LLM-Anbieter</span></button>
        <button class="a26-nav-row" type="button"><span>LLM-Routing</span></button>
      </div>

      <div class="a26-rail-foot">
        <div class="a26-user-chip">
          <div class="avatar">AD</div>
          <div class="who">
            <span class="name">Alex Dietzel</span>
            <span class="org">alexle135.de · admin</span>
          </div>
          <span class="more"><Icon name="more" /></span>
        </div>
      </div>
    </aside>

    <!-- Canvas -->
    <main class="a26-canvas">
      <div class="a26-topbar">
        <div class="a26-crumbs">
          <template v-for="(c, i) in crumbs" :key="i">
            <span v-if="i > 0" class="sep">/</span>
            <span :class="{ here: i === crumbs.length - 1 }">{{ c }}</span>
          </template>
        </div>

        <div class="a26-topbar-spacer" />

        <slot name="extra" />

        <div class="a26-search">
          <Icon name="search" />
          <span>Suche · Runs, Projekte, Vorlagen</span>
          <span class="kbd">⌘ K</span>
        </div>

        <ModelPill :provider="modelProvider" :model="modelName" :label="modelLabel" />

        <button type="button" class="a26-ico-btn" title="Benachrichtigungen">
          <Icon name="bell" />
          <span class="badge" />
        </button>
        <button type="button" class="a26-ico-btn"><Icon name="more" /></button>
      </div>

      <div :class="padless ? '' : 'a26-page'">
        <slot />
      </div>
    </main>
  </div>
</template>
