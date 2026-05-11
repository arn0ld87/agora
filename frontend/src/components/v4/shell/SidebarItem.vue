<template>
  <component
    :is="to ? 'RouterLink' : 'div'"
    v-bind="to ? { to } : {}"
    class="sidebar-item"
    :class="{ 'sidebar-item--active': active }"
    @click="!to && emit('click')"
  >
    <Icon v-if="icon" :name="icon" :size="18" :stroke="1.6" />
    <span class="sidebar-item__label">{{ label }}</span>
    <span v-if="badge != null && badge > 0" class="sidebar-item__badge">{{ badge }}</span>
  </component>
</template>

<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'
import Icon from './Icon.vue'
import type { IconName } from './Icon.vue'

defineProps<{
  icon?: IconName | string
  label: string
  badge?: number
  to?: RouteLocationRaw
  active?: boolean
}>()

const emit = defineEmits<{
  click: []
}>()
</script>

<style scoped>
.sidebar-item {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 36px;
  padding: 0 10px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  background: transparent;
  text-decoration: none;
  cursor: pointer;
  transition: background 100ms ease, color 100ms ease;
  user-select: none;
}

.sidebar-item:hover:not(.sidebar-item--active) {
  background: var(--surface-hover, rgba(0, 0, 0, 0.04));
}

.sidebar-item--active {
  background: var(--accent-tint-bg);
  color: var(--accent);
  font-weight: 600;
}

.sidebar-item__label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-item__badge {
  min-width: 18px;
  height: 18px;
  border-radius: 9px;
  background: var(--accent);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 5px;
}
</style>
