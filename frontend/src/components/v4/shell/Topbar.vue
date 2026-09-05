<template>
  <header class="topbar">
    <!-- Hamburger-Button (nur Mobile) -->
    <button
      class="topbar__hamburger"
      type="button"
      :aria-label="t('topbar.openNavigation')"
      :aria-expanded="shellStore.mobileNavOpen"
      @click="shellStore.toggleMobileNav()"
    >
      <Icon name="menu" :size="20" :stroke="1.6" />
    </button>

    <!-- Crumbs (left) -->
    <div class="topbar__crumbs">
      <slot name="crumbs">
        <Breadcrumbs :crumbs="breadcrumbs" />
      </slot>
    </div>

    <!-- Actions (right) -->
    <div class="topbar__actions">
      <slot name="actions">
        <!-- Protokoll → oeffnet den Log-Drawer (Redesign PR 2: ex-FAB in App.vue) -->
        <button
          class="topbar__icon-btn"
          type="button"
          :aria-label="t('logs.drawer.toggle')"
          :title="t('logs.drawer.toggle')"
          :data-testid="ShellTestId.logsTrigger"
          @click="toggleLogDrawer"
        >
          <Icon name="logs" :size="20" :stroke="1.6" />
        </button>

        <!-- Search → oeffnet Command-Palette; ⌘K-Chip einheitlich mit ShellRoot.vue -->
        <button
          class="topbar__icon-btn topbar__cmdk"
          type="button"
          :aria-label="t('topbar.search')"
          :title="t('cmd.trigger')"
          :data-testid="ShellTestId.cmdkTrigger"
          @click="openPalette"
        >
          {{ t('topbar.search') }}
          <span class="kbd">⌘K</span>
        </button>

        <!-- User slot -->
        <div class="topbar__user">
          <slot name="user">
            <!-- Dichte-Umschalter bleibt, solange die klassische Huelle
                 der Standard ist: die neue Shell steht hinter einem Flag,
                 und ohne dieses Bedienelement gaebe es fuer klassische
                 Nutzer keinen Weg mehr zwischen kompakt und komfortabel.
                 Faellt mit der Huelle. -->
            <DensityToggle />

            <UserMenu />
          </slot>
        </div>
      </slot>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Breadcrumbs from './Breadcrumbs.vue'
import type { BreadcrumbItem } from './Breadcrumbs.vue'
import Icon from './Icon.vue'
import DensityToggle from './DensityToggle.vue'
import UserMenu from '@/components/shell/UserMenu.vue'
import { useCommandPalette } from '@/composables/useCommandPalette'
import { useLogDrawer } from '@/composables/useLogDrawer'
import { useShellStore } from '@/stores/shell'
import { ShellTestId } from '@/contracts/testIds'

const { t } = useI18n()
const { open: openPalette } = useCommandPalette()
const { toggle: toggleLogDrawer } = useLogDrawer()
const shellStore = useShellStore()

withDefaults(
  defineProps<{
    breadcrumbs?: BreadcrumbItem[]
  }>(),
  {
    breadcrumbs: () => [],
  },
)

</script>

<style scoped>
.topbar {
  height: var(--topbar-h, 64px);
  padding: 0 var(--topbar-px, 24px);
  background: var(--surface-base, #fff);
  border-bottom: 1px solid var(--hairline);
  display: flex;
  align-items: center;
  gap: 12px;
  transition: height var(--v4-state-motion-duration-fast) var(--v4-state-motion-ease),
    padding var(--v4-state-motion-duration-fast) var(--v4-state-motion-ease);
}

.topbar__crumbs {
  flex: 1;
  display: flex;
  align-items: center;
  min-width: 0;
}

.topbar__actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.topbar__icon-btn {
  width: var(--ctl-h-lg);
  height: var(--ctl-h-lg);
  border-radius: 8px;
  background: transparent;
  border: 0;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background var(--v4-state-motion-duration-fast) var(--v4-state-motion-ease),
    color var(--v4-state-motion-duration-fast) var(--v4-state-motion-ease);
  padding: 0;
}

.topbar__icon-btn:hover {
  background: var(--surface-hover, rgba(0, 0, 0, 0.04));
  color: var(--text-primary);
}

/* ⌘K-Chip: Variante von .topbar__icon-btn mit Text+Kbd statt fixem
   Icon-Quadrat — Markup/Styling einheitlich mit ShellRoot.vue. */
.topbar__cmdk {
  width: auto;
  padding: 0 var(--sp-3, 10px);
  gap: 6px;
  font-family: var(--font-sans);
  font-size: var(--fs-small);
}

.kbd {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  border: 1px solid var(--border-strong);
  border-radius: 3px;
  padding: 1px 5px;
}

.topbar__user {
  margin-left: 8px;
}

/* Hamburger: standardmaessig versteckt, nur auf Mobile sichtbar */
.topbar__hamburger {
  display: none;
  width: var(--ctl-h-lg);
  height: var(--ctl-h-lg);
  border-radius: 8px;
  background: transparent;
  border: 0;
  color: var(--text-secondary);
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background var(--v4-state-motion-duration-fast) var(--v4-state-motion-ease),
    color var(--v4-state-motion-duration-fast) var(--v4-state-motion-ease);
  padding: 0;
  flex-shrink: 0;
}

.topbar__hamburger:hover {
  background: var(--surface-hover, rgba(0, 0, 0, 0.04));
  color: var(--text-primary);
}

/* SSoT: src/constants/breakpoints.ts (MOBILE_BREAKPOINT_PX = 768) —
   max-width: 767px bildet "< 768" ab (Slice 7.3.2, Breakpoint-Vereinheitlichung). */
@media (max-width: 767px) {
  .topbar {
    padding: 0 12px;
    height: 56px;
  }

  .topbar__hamburger {
    display: inline-flex;
  }
}

.topbar__usermenu {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
</style>
