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
        <!-- Aktivitaets-Indikator der Ablage (#1795, ex ShellRoot) -->
        <ShelfActivity />

        <!-- Suche (Cmd+K) → öffnet die Befehlspalette. Ab 1024 px abwärts
             nur noch als Symbolknopf (Bauplan Abschnitt 11). -->
        <button
          v-if="compact"
          class="topbar__icon-btn"
          type="button"
          :aria-label="t('topbar.searchShort')"
          :title="t('topbar.searchShort')"
          :data-testid="ShellTestId.cmdkTrigger"
          @click="openPalette"
        >
          <svg aria-hidden="true" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6">
            <circle cx="7" cy="7" r="5" />
            <line x1="11" y1="11" x2="14.5" y2="14.5" />
          </svg>
        </button>
        <button
          v-else
          class="topbar__search"
          type="button"
          :aria-label="t('topbar.search')"
          :title="t('cmd.trigger')"
          :data-testid="ShellTestId.cmdkTrigger"
          @click="openPalette"
        >
          <svg aria-hidden="true" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6">
            <circle cx="7" cy="7" r="5" />
            <line x1="11" y1="11" x2="14.5" y2="14.5" />
          </svg>
          <span class="topbar__search-label">{{ t('topbar.search') }}</span>
          <span class="kbd">⌘K</span>
        </button>

        <!-- Neuer Lauf → bestehender Start eines Laufs (Dashboard mit HeroNewRun) -->
        <button
          class="topbar__primary"
          type="button"
          data-testid="topbar-new-run"
          @click="startNewRun"
        >
          <span class="topbar__primary-plus" aria-hidden="true">+</span>
          {{ t('topbar.newRun') }}
        </button>

        <!-- Konsole → Log-Drawer; Plakette mit ungelesenen Fehlern (nur Operator) -->
        <button
          v-if="logsAvailable"
          class="topbar__console"
          type="button"
          :aria-pressed="logsOpen"
          :aria-label="consoleLabel"
          :title="t('logs.drawer.toggle')"
          :data-testid="ShellTestId.logsTrigger"
          @click="toggleLogDrawer"
        >
          <span class="topbar__console-glyph" aria-hidden="true">&gt;_</span>
          <span class="topbar__console-label">{{ t('topbar.console') }}</span>
          <span
            v-if="unreadErrors > 0"
            class="topbar__badge"
            data-testid="topbar-console-badge"
            aria-hidden="true"
          >{{ unreadErrors }}</span>
        </button>

        <!-- Profilmenü: Konto, Workspace, Darstellung (inkl. Dichte), Abmelden -->
        <div class="topbar__user">
          <slot name="user">
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
import { useRouter } from 'vue-router'
import Breadcrumbs from './Breadcrumbs.vue'
import type { BreadcrumbItem } from './Breadcrumbs.vue'
import Icon from './Icon.vue'
import UserMenu from '@/components/shell/UserMenu.vue'
import ShelfActivity from '@/components/shell/ShelfActivity.vue'
import { useCommandPalette } from '@/composables/useCommandPalette'
import { useCompactToolbar } from '@/composables/useCompactToolbar'
import { useLogDrawer } from '@/composables/useLogDrawer'
import { useShellStore } from '@/stores/shell'
import { ShellTestId } from '@/contracts/testIds'

const { t } = useI18n()
const router = useRouter()
const { open: openPalette } = useCommandPalette()
const {
  toggle: toggleLogDrawer,
  available: logsAvailable,
  isOpen: logsOpen,
  unreadErrors,
} = useLogDrawer()
const { compact } = useCompactToolbar()
const shellStore = useShellStore()

withDefaults(
  defineProps<{
    breadcrumbs?: BreadcrumbItem[]
  }>(),
  {
    breadcrumbs: () => [],
  },
)

const consoleLabel = computed(() =>
  unreadErrors.value > 0
    ? `${t('topbar.consoleToggle')}, ${t('topbar.consoleUnread', { count: unreadErrors.value })}`
    : t('topbar.consoleToggle'),
)

/** Ein neuer Lauf beginnt heute im Dashboard (HeroNewRun → Process/new). */
function startNewRun(): void {
  void router.push({ name: 'Dashboard' })
}
</script>

<style scoped>
.topbar {
  height: var(--topbar-h, 64px);
  padding: 0 var(--topbar-px, 24px);
  background: var(--surface-base);
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
  gap: 8px;
  flex-shrink: 0;
}

.topbar__icon-btn,
.topbar__search,
.topbar__console,
.topbar__primary {
  height: 32px;
  border: 0;
  border-radius: var(--ag-r-8, 8px);
  display: inline-flex;
  align-items: center;
  font-family: var(--ag-font-sans, var(--font-sans));
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
}

.topbar__icon-btn,
.topbar__search {
  background: var(--s2, transparent);
  color: var(--fg3, var(--text-secondary));
}

.topbar__icon-btn {
  width: 32px;
  justify-content: center;
  padding: 0;
  color: var(--fg2, var(--text-secondary));
}

.topbar__search {
  width: 220px;
  gap: 8px;
  padding: 0 8px 0 10px;
  box-sizing: border-box;
}

.topbar__search-label {
  flex: 1;
  text-align: left;
}

.topbar__icon-btn:hover,
.topbar__search:hover,
.topbar__console:hover {
  background: var(--s3, var(--surface-hover));
}

.kbd {
  font-family: var(--ag-font-mono, var(--font-mono));
  font-size: 11px;
  padding: 1px 6px;
  border-radius: var(--ag-r-6, 5px);
  background: var(--s3, transparent);
  color: var(--fg2, var(--text-muted));
}

.topbar__console {
  gap: 8px;
  padding: 0 8px 0 10px;
  background: transparent;
  color: var(--fg, var(--text-primary));
}

.topbar__console[aria-pressed='true'] {
  background: var(--s2, var(--surface-hover));
}

.topbar__console-glyph {
  font-family: var(--ag-font-mono, var(--font-mono));
  font-size: 12px;
  color: var(--fg2, var(--text-secondary));
}

.topbar__badge {
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  box-sizing: border-box;
  border-radius: var(--ag-r-pill, 999px);
  display: grid;
  place-items: center;
  font-size: 11px;
  font-weight: 600;
  background: var(--err, var(--s4));
  color: var(--on-acc, var(--fg));
}

.topbar__primary {
  gap: 6px;
  padding: 0 14px 0 12px;
  background: var(--acc, var(--accent));
  color: var(--on-acc, var(--text-primary));
  font-weight: 600;
}

.topbar__primary:hover {
  background: var(--acc-hover, var(--acc, var(--accent)));
}

.topbar__primary:active {
  background: var(--acc-press, var(--acc, var(--accent)));
}

.topbar__primary-plus {
  font-size: 16px;
  line-height: 1;
}

.topbar__icon-btn:focus-visible,
.topbar__search:focus-visible,
.topbar__console:focus-visible,
.topbar__primary:focus-visible,
.topbar__hamburger:focus-visible {
  outline: 2px solid var(--acc, var(--accent));
  outline-offset: 2px;
}

.topbar__user {
  margin-left: 4px;
}

/* Hamburger: standardmaessig versteckt, nur auf Mobile sichtbar */
.topbar__hamburger {
  display: none;
  width: var(--ctl-h-lg);
  height: var(--ctl-h-lg);
  border-radius: var(--r-3);
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
  background: var(--surface-hover);
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

  .topbar__console-label {
    display: none;
  }
}
</style>
