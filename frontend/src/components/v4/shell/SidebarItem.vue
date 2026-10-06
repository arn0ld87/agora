<template>
  <component
    :is="componentTag"
    v-bind="componentAttrs"
    class="sidebar-item v4-state-selectable"
    :class="componentClasses"
    @click="handleClick"
  >
    <span v-if="tone" class="sidebar-item__dot" :class="`sidebar-item__dot--${tone}`" aria-hidden="true" />
    <span v-else-if="glyph" class="sidebar-item__glyph" aria-hidden="true">{{ glyph }}</span>
    <Icon v-else-if="icon" :name="icon" :size="18" :stroke="1.6" />
    <span v-if="!collapsed" class="sidebar-item__label">{{ label }}</span>
    <!-- Der Zustandspunkt ist aria-hidden: den Zustand liest die Hilfstechnik hier. -->
    <span v-if="!collapsed && tone && tooltip" class="sidebar-item__sr">{{ tooltip }}</span>
    <!-- Zaehler: neutral gefaerbt. null/undefined = unbekannt, dann gar keine Zahl (nie „0“ vortaeuschen). -->
    <span v-if="!collapsed && count != null" class="sidebar-item__count">{{ count }}</span>
    <span v-if="badge != null && badge > 0" class="sidebar-item__badge">{{ badge }}</span>
  </component>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useLink } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import Icon from './Icon.vue'
import type { IconName } from './Icon.vue'

const props = withDefaults(defineProps<{
  icon?: IconName | string
  /** Zeichen im runden Platzhalter (Entwurf der Seitenleiste); hat Vorrang vor `icon`. */
  glyph?: string
  label: string
  badge?: number
  /** Neutraler Zaehler hinter dem Label; `null` = unbekannt, es wird keine Zahl gezeigt. */
  count?: number | null
  /** Auf Symbole eingeklappt: nur Symbol, Name und Zaehler wandern in aria-label/title. */
  collapsed?: boolean
  /** Zustandspunkt statt Symbol (System-Eintrag). */
  tone?: 'ok' | 'err' | 'unknown'
  to?: RouteLocationRaw
  active?: boolean
  /**
   * Erzwingt den aktiven Zustand. Ohne diese Angabe leitet der Eintrag ihn aus dem
   * Router ab; der Router kennt aber keine Query — mehrere Eintraege auf `/ablage?filter=…`
   * waeren sonst alle gleichzeitig aktiv.
   */
  current?: boolean
  /** Deaktiviert den Item: kein Router-Push, aria-disabled="true", gedimmtes Styling. */
  disabled?: boolean
  /** Tooltip-Text (z. B. „Bald verfügbar“). */
  tooltip?: string
}>(), {
  // Ohne Default wuerde Vue ein fehlendes Boolean-Prop zu `false` machen und
  // „nicht angegeben“ (aus dem Router ableiten) von „nicht aktiv“ nicht trennen.
  current: undefined,
})

const emit = defineEmits<{
  click: []
}>()

// useLink braucht immer eine Route — Fallback auf '/' wenn kein 'to' gesetzt ist.
// Die Werte werden nur genutzt wenn props.to gesetzt ist.
const linkTarget = computed(() => props.to ?? '/')
const { isExactActive, isActive } = useLink({ to: linkTarget })

const isCurrent = computed(() => {
  if (props.current !== undefined) return props.current
  return props.to ? isExactActive.value || isActive.value || !!props.active : !!props.active
})

/** Zugaenglicher Name: eingeklappt fehlt das sichtbare Label, der Zaehler gehoert dazu. */
const collapsedName = computed(() => {
  if (props.tone && props.tooltip) return `${props.label}: ${props.tooltip}`
  return props.count != null ? `${props.label}, ${props.count}` : props.label
})

const componentTag = computed(() => {
  if (props.disabled) return 'span'
  if (props.to) return RouterLink
  return 'div'
})

const componentAttrs = computed(() => {
  const named = props.collapsed
    ? { 'aria-label': collapsedName.value, title: props.tone ? collapsedName.value : (props.tooltip ?? collapsedName.value) }
    : { title: props.tooltip }
  if (props.disabled) {
    return { ...named, 'aria-disabled': 'true' }
  }
  if (props.to) {
    return {
      ...named,
      to: props.to,
      'aria-current': isCurrent.value ? 'page' : undefined,
    }
  }
  return named
})

const componentClasses = computed(() => ({
  'sidebar-item--active': isCurrent.value,
  'sidebar-item--collapsed': !!props.collapsed,
  'sidebar-item--disabled': !!props.disabled,
}))

function handleClick() {
  if (props.disabled) return
  // Mit `to` navigiert RouterLink selbst; `click` melden wir trotzdem, damit die
  // Seitenleiste den mobilen Drawer nach der Navigation schliessen kann.
  emit('click')
}
</script>

<style scoped>
.sidebar-item {
  position: relative;
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
  text-decoration: none;
  cursor: pointer;
  /* transition: via .v4-state-selectable */
  user-select: none;
}

.sidebar-item--collapsed {
  justify-content: center;
}

.sidebar-item:hover:not(.sidebar-item--active) {
  background: var(--s3);
}

.sidebar-item--active {
  background: var(--acc-soft);
  color: var(--fg);
  font-weight: 600;
}

.sidebar-item:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

.sidebar-item__glyph {
  width: 24px;
  height: 24px;
  border-radius: var(--ag-r-pill);
  display: grid;
  place-items: center;
  flex: none;
  font-size: 11px;
  background: var(--s3);
  color: var(--fg2);
}

.sidebar-item--active .sidebar-item__glyph {
  background: var(--acc);
  color: var(--on-acc);
}

.sidebar-item__dot {
  width: 8px;
  height: 8px;
  margin: 0 8px;
  border-radius: var(--ag-r-pill);
  flex: none;
  background: var(--fg3);
}

.sidebar-item__dot--ok {
  background: var(--ok);
}

.sidebar-item__dot--err {
  background: var(--err);
}

.sidebar-item__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.sidebar-item__label {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Neutral gefaerbt, auch bei „Braucht dich“ (Abweichung Durchgang 1): die Zahl zaehlt, sie alarmiert nicht. */
.sidebar-item__count {
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  box-sizing: border-box;
  border-radius: var(--ag-r-pill);
  display: grid;
  place-items: center;
  font-size: 11.5px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--fg3);
}

/* Disabled: Token-Override */
.sidebar-item--disabled {
  opacity: var(--v4-state-disabled-opacity);
  cursor: var(--v4-state-disabled-cursor);
  color: var(--fg2);
}

.sidebar-item--disabled:hover {
  background: transparent;
}

.sidebar-item__badge {
  min-width: 18px;
  height: 18px;
  border-radius: var(--ag-r-pill);
  background: var(--acc);
  color: var(--on-acc);
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 5px;
}
</style>
