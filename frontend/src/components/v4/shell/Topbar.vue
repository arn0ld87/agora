<template>
  <header class="topbar">
    <!-- Crumbs (left) -->
    <div class="topbar__crumbs">
      <slot name="crumbs">
        <Breadcrumbs :crumbs="breadcrumbs" />
      </slot>
    </div>

    <!-- Actions (right) -->
    <div class="topbar__actions">
      <slot name="actions">
        <!-- Search → oeffnet Command-Palette -->
        <button
          class="topbar__icon-btn"
          type="button"
          :aria-label="t('topbar.search')"
          :title="t('cmd.trigger')"
          @click="openPalette"
        >
          <Icon name="search" :size="18" :stroke="1.6" />
        </button>

        <!-- Notifications with badge -->
        <div class="topbar__notif-wrap">
          <button class="topbar__icon-btn" type="button" :aria-label="t('topbar.notifications')">
            <!-- Bell icon inline (not in ds-shell registry, built-in) -->
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
              <path d="M10 3C7.24 3 5 5.24 5 8V12L3 14V15H17V14L15 12V8C15 5.24 12.76 3 10 3Z"
                stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M8.5 16.5C8.5 17.33 9.17 18 10 18C10.83 18 11.5 17.33 11.5 16.5"
                stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
            </svg>
          </button>
          <span v-if="notificationBadge > 0" class="topbar__badge" :aria-label="`${notificationBadge} ${t('topbar.notifications')}`">
            {{ notificationBadge }}
          </span>
        </div>

        <!-- Density Toggle -->
        <DensityToggle />

        <!-- User slot -->
        <div class="topbar__user">
          <slot name="user">
            <div class="topbar__avatar" aria-hidden="true">AD</div>
          </slot>
        </div>
      </slot>
    </div>
  </header>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import Breadcrumbs from './Breadcrumbs.vue'
import type { BreadcrumbItem } from './Breadcrumbs.vue'
import Icon from './Icon.vue'
import DensityToggle from './DensityToggle.vue'
import { useCommandPalette } from '@/composables/useCommandPalette'

const { t } = useI18n()
const { open: openPalette } = useCommandPalette()

withDefaults(
  defineProps<{
    breadcrumbs?: BreadcrumbItem[]
    notificationBadge?: number
  }>(),
  {
    breadcrumbs: () => [],
    notificationBadge: 0,
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
  transition: height 150ms ease, padding 150ms ease;
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
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: transparent;
  border: 0;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 100ms ease, color 100ms ease;
  padding: 0;
}

.topbar__icon-btn:hover {
  background: var(--surface-hover, rgba(0, 0, 0, 0.04));
  color: var(--text-primary);
}

.topbar__notif-wrap {
  position: relative;
}

.topbar__badge {
  position: absolute;
  top: 4px;
  right: 4px;
  min-width: 16px;
  height: 16px;
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
  box-shadow: 0 0 0 2px var(--surface-base, #fff);
  pointer-events: none;
}

.topbar__user {
  margin-left: 8px;
}

.topbar__avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--accent-tint-bg);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
