<script setup lang="ts">
/**
 * Tabs — URL-synced Tab-Navigation für Agora Design v4
 * Source-Truth: ds-screens-a.jsx Inline-Page-Tabs-Style
 * Slice D · 2026-05-11
 *
 * URL-Sync: schreibt/liest Query-Param (default: 'tab').
 * Wenn urlSync=false → rein lokaler v-model-State.
 */

import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

export interface TabItem {
  key: string
  label: string
  badge?: string | number
  disabled?: boolean
}

const props = withDefaults(
  defineProps<{
    modelValue: string
    tabs: TabItem[]
    /** Query-Param-Name für URL-Sync */
    param?: string
    urlSync?: boolean
  }>(),
  {
    param: 'tab',
    urlSync: true,
  },
)

const emit = defineEmits<{
  'update:modelValue': [key: string]
}>()

const route = useRoute()
const router = useRouter()

// Beim Mount: wenn URL-Param gesetzt und urlSync aktiv → emit
if (props.urlSync) {
  const urlTab = route.query[props.param]
  if (typeof urlTab === 'string' && urlTab && urlTab !== props.modelValue) {
    const valid = props.tabs.find((t) => t.key === urlTab && !t.disabled)
    if (valid) {
      emit('update:modelValue', urlTab)
    }
  }
}

// modelValue → URL synchronisieren
watch(
  () => props.modelValue,
  (key) => {
    if (!props.urlSync) return
    const current = route.query[props.param]
    if (current !== key) {
      router.replace({
        query: { ...route.query, [props.param]: key },
      })
    }
  },
  { immediate: false },
)

function select(tab: TabItem): void {
  if (tab.disabled) return
  emit('update:modelValue', tab.key)
}

function isActive(tab: TabItem): boolean {
  return tab.key === props.modelValue
}
</script>

<template>
  <div class="tabs-bar" role="tablist">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      role="tab"
      class="tabs-item v4-state-selectable"
      :class="{
        'tabs-item--active': isActive(tab),
        'tabs-item--disabled': tab.disabled,
      }"
      :aria-selected="isActive(tab)"
      :aria-disabled="tab.disabled"
      :disabled="tab.disabled"
      @click="select(tab)"
    >
      {{ tab.label }}
      <span v-if="tab.badge !== undefined && tab.badge !== ''" class="tabs-badge">
        {{ tab.badge }}
      </span>
    </button>
  </div>
</template>

<style scoped>
.tabs-bar {
  display: flex;
  gap: 24px;
  border-bottom: 1px solid var(--hairline);
  padding-bottom: 0;
}

.tabs-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 4px;
  font-size: 14px;
  font-weight: 500;
  font-family: var(--font-sans);
  color: var(--text-secondary);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px; /* überdeckt den Container-Border */
  cursor: pointer;
  white-space: nowrap;
  transition: color 100ms ease, border-color 100ms ease;
  outline: none;
}

/* Hover: v4-state-selectable liefert BG; Tab-Farbe zusätzlich */
.tabs-item:hover:not(.tabs-item--active):not(.tabs-item--disabled) {
  color: var(--v4-state-hover-fg);
}

.tabs-item--active {
  color: var(--text-primary);
  font-weight: 600;
  border-bottom-color: var(--accent);
}

/* Disabled: Token-Override */
.tabs-item--disabled {
  opacity: var(--v4-state-disabled-opacity);
  cursor: var(--v4-state-disabled-cursor);
}

/* Focus: Override für korrekten Offset + Border-Radius bei Tab-Geometrie */
.tabs-item:focus-visible {
  outline: var(--v4-state-focus-ring-width) solid var(--v4-state-focus-ring);
  outline-offset: var(--v4-state-focus-ring-offset);
  border-radius: var(--r-3);
}

/* ── Badge ──────────────────────────────────────────────────── */

.tabs-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--surface-inset);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 500;
  font-family: var(--font-sans);
  padding: 1px 6px;
  border-radius: var(--r-pill, 999px);
  line-height: 1.4;
  min-width: 18px;
}

.tabs-item--active .tabs-badge {
  background: var(--accent-tint-bg);
  color: var(--accent-tint-text);
}
</style>
