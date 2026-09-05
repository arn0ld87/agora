<template>
  <component
    :is="componentTag"
    v-bind="componentAttrs"
    class="sidebar-item v4-state-selectable"
    :class="componentClasses"
    @click="handleClick"
  >
    <Icon v-if="icon" :name="icon" :size="18" :stroke="1.6" />
    <span class="sidebar-item__label">{{ label }}</span>
    <span v-if="badge != null && badge > 0" class="sidebar-item__badge">{{ badge }}</span>
  </component>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useLink } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import Icon from './Icon.vue'
import type { IconName } from './Icon.vue'

const props = defineProps<{
  icon?: IconName | string
  label: string
  badge?: number
  to?: RouteLocationRaw
  active?: boolean
  /** Deaktiviert den Item: kein Router-Push, aria-disabled="true", gedimmtes Styling. */
  disabled?: boolean
  /** Tooltip-Text (z. B. „Bald verfügbar“). */
  tooltip?: string
}>()

const emit = defineEmits<{
  click: []
}>()

// useLink braucht immer eine Route — Fallback auf '/' wenn kein 'to' gesetzt ist.
// Die Werte werden nur genutzt wenn props.to gesetzt ist.
const linkTarget = computed(() => props.to ?? '/')
const { isExactActive, isActive } = useLink({ to: linkTarget })

const componentTag = computed(() => {
  if (props.disabled) return 'span'
  if (props.to) return RouterLink
  return 'div'
})

const componentAttrs = computed(() => {
  if (props.disabled) {
    return {
      'aria-disabled': 'true',
      title: props.tooltip,
    }
  }
  if (props.to) {
    return {
      to: props.to,
      'aria-current': isExactActive.value ? 'page' : (isActive.value ? 'true' : undefined),
      title: props.tooltip,
    }
  }
  return {
    title: props.tooltip,
  }
})

const componentClasses = computed(() => ({
  'sidebar-item--active': props.to
    ? (isExactActive.value || isActive.value || !!props.active)
    : !!props.active,
  'sidebar-item--disabled': !!props.disabled,
}))

function handleClick(event: MouseEvent) {
  if (props.disabled) return
  if (props.to) {
    // navigate handled by RouterLink itself
    return
  }
  emit('click')
}
</script>

<style scoped>
.sidebar-item {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 36px;
  padding: var(--sidebar-item-py, 6px) var(--sidebar-item-px, 10px);
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  background: transparent;
  text-decoration: none;
  cursor: pointer;
  /* transition: via .v4-state-selectable */
  user-select: none;
}

/* Hover: v4-state-selectable liefert BG-Token */
.sidebar-item:hover:not(.sidebar-item--active) {
  background: var(--v4-state-hover-bg);
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

/* Disabled: Token-Override */
.sidebar-item--disabled {
  opacity: var(--v4-state-disabled-opacity);
  cursor: var(--v4-state-disabled-cursor);
  color: var(--text-secondary);
}

.sidebar-item--disabled:hover {
  background: transparent;
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
