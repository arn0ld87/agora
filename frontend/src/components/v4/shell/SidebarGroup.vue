<template>
  <div class="sidebar-group">
    <!-- Group header trigger -->
    <div
      :id="`sidebar-group-trigger-${groupKey}`"
      class="sidebar-group__trigger"
      :class="{ 'sidebar-group__trigger--active': isGroupOpen(groupKey) }"
      role="button"
      tabindex="0"
      :aria-expanded="isGroupOpen(groupKey)"
      :aria-controls="`sidebar-group-body-${groupKey}`"
      data-sidebar-trigger
      @click="toggleGroup(groupKey)"
      @keydown.enter.prevent="toggleGroup(groupKey)"
      @keydown.space.prevent="toggleGroup(groupKey)"
    >
      <Icon v-if="icon" :name="icon" :size="18" :stroke="1.6" />
      <span class="sidebar-group__label">{{ label }}</span>
      <Icon
        :name="isGroupOpen(groupKey) ? 'chevronD' : 'chevron'"
        :size="12"
        :stroke="1.6"
        class="sidebar-group__chevron"
      />
    </div>

    <!-- Sub-items -->
    <div
      v-if="isGroupOpen(groupKey)"
      :id="`sidebar-group-body-${groupKey}`"
      class="sidebar-group__body"
    >
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import Icon from './Icon.vue'
import type { IconName } from './Icon.vue'
import { useSidebarState } from '@/composables/useSidebarState'

const props = defineProps<{
  groupKey: string
  label: string
  icon?: IconName | string
  activeRouteNames: string[]
}>()

const route = useRoute()
const { isGroupOpen, setGroupOpen, toggleGroup } = useSidebarState()

const hasActiveChild = computed(() =>
  props.activeRouteNames.length > 0 &&
  route.matched.some(
    (r) => r.name !== undefined && props.activeRouteNames.includes(String(r.name)),
  ),
)

onMounted(() => {
  if (hasActiveChild.value) {
    setGroupOpen(props.groupKey, true)
  }
})

// Reaktiv auf Route-Wechsel: Auto-Open wenn ein Child-Route aktiv wird.
watch(hasActiveChild, (active) => {
  if (active) setGroupOpen(props.groupKey, true)
})
</script>

<style scoped>
.sidebar-group__trigger {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 32px;
  padding: 0 8px;
  border-radius: var(--ag-r-8);
  font-size: 13.5px;
  font-weight: 400;
  color: var(--fg);
  background: transparent;
  cursor: pointer;
  user-select: none;
  transition: background 100ms ease;
}

.sidebar-group__trigger:hover:not(.sidebar-group__trigger--active) {
  background: var(--s3);
}

.sidebar-group__trigger--active {
  background: var(--acc-soft);
  color: var(--fg);
  font-weight: 600;
}

.sidebar-group__label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-group__chevron {
  flex-shrink: 0;
}

.sidebar-group__body {
  display: flex;
  flex-direction: column;
  gap: 0;
  margin-top: 2px;
}

/* Sub-item styling via ::slotted */
.sidebar-group__body :deep(.sidebar-sub-item) {
  display: flex;
  align-items: center;
  height: 28px;
  padding: 0 10px 0 42px;
  border-radius: var(--ag-r-8);
  font-size: 13px;
  font-weight: 400;
  color: var(--fg);
  background: transparent;
  text-decoration: none;
  cursor: pointer;
  border-left: 2px solid transparent;
  transition: background 100ms ease, color 100ms ease;
  user-select: none;
}

.sidebar-group__body :deep(.sidebar-sub-item:hover:not(.sidebar-sub-item--active)) {
  background: var(--s3);
}

.sidebar-group__body :deep(.sidebar-sub-item--active) {
  background: var(--acc-soft);
  color: var(--fg);
  font-weight: 600;
  border-left-color: var(--acc);
}

/* Der Gruppen-Auslöser ist ein <button> ohne jede Fokusregel gewesen. */
.sidebar-group__trigger:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}
</style>
