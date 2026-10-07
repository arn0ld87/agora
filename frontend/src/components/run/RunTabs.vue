<script setup lang="ts">
/**
 * Reiterleiste des Lauf-Arbeitsbereichs: Navigation (kein ARIA-tablist),
 * `aria-current="page"` am aktiven Reiter, Tab-Taste läuft in DOM-Reihenfolge.
 * Nicht auflösbare Ziele sind sichtbar deaktiviert und nennen den Grund; sie
 * bleiben fokussierbar, damit der Grund auch per Tastatur erreichbar ist.
 */
import { useRoute, type RouteLocationRaw } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { RunTab } from '@/composables/run/runTabs'

defineProps<{ tabs: RunTab[] }>()
const { t } = useI18n()
const route = useRoute()

function isActive(tab: RunTab): boolean {
  if (!tab.to) return false
  // Alle Unterreiter der Simulation (Feed, Beitrag, Runden, Diagnose) gehoeren zum Reiter.
  if (tab.key === 'simulation') return route.matched.some((r) => r.name === 'RunSimulation')
  return route.name === tab.to.name
}
</script>

<template>
  <nav class="run-tabs" :aria-label="t('views.run.tabs.label')" data-testid="run-tabs">
    <template v-for="tab in tabs" :key="tab.key">
      <router-link v-if="tab.to" v-slot="{ href, navigate }" custom :to="tab.to as RouteLocationRaw">
        <a
          :href="href"
          class="run-tabs__tab"
          :class="{ 'run-tabs__tab--active': isActive(tab) }"
          :aria-current="isActive(tab) ? 'page' : undefined"
          :data-testid="`run-tab-${tab.key}`"
          @click="navigate"
        >
          {{ t(`views.run.tabs.${tab.key}`) }}
        </a>
      </router-link>
      <button
        v-else
        type="button"
        class="run-tabs__tab run-tabs__tab--disabled"
        aria-disabled="true"
        :aria-describedby="`run-tab-reason-${tab.key}`"
        :title="t(`views.run.disabled.${tab.disabledReason}`)"
        :data-testid="`run-tab-${tab.key}`"
      >
        {{ t(`views.run.tabs.${tab.key}`) }}
        <span :id="`run-tab-reason-${tab.key}`" class="run-tabs__reason">
          {{ t(`views.run.disabled.${tab.disabledReason}`) }}
        </span>
      </button>
    </template>
  </nav>
</template>

<style scoped>
.run-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 0 0 18px;
}
.run-tabs__tab {
  display: inline-flex;
  align-items: center;
  height: 34px;
  padding: 0 14px;
  border: none;
  border-radius: var(--ag-r-8);
  background: transparent;
  color: var(--fg2);
  font: inherit;
  font-size: 13.5px;
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
}
.run-tabs__tab:hover {
  background: var(--s2);
  color: var(--fg);
}
.run-tabs__tab:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.run-tabs__tab--active {
  background: var(--s3);
  color: var(--fg);
  font-weight: 650;
}
.run-tabs__tab--disabled {
  color: var(--fg3);
  cursor: not-allowed;
  text-decoration: line-through;
  text-decoration-thickness: 1px;
}
.run-tabs__tab--disabled:hover {
  background: transparent;
  color: var(--fg3);
}
.run-tabs__reason {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
