<template>
  <nav class="breadcrumbs" aria-label="Breadcrumb">
    <ol class="breadcrumbs__list">
      <template v-for="(crumb, idx) in resolvedCrumbs" :key="crumb.to ?? crumb.label">
        <li
          v-if="idx > 0"
          class="breadcrumbs__sep"
          aria-hidden="true"
        >/</li>
        <li
          class="breadcrumbs__item"
          :class="{ 'breadcrumbs__item--last': idx === resolvedCrumbs.length - 1 }"
          data-crumb
          :aria-current="idx === resolvedCrumbs.length - 1 ? 'page' : undefined"
        >{{ crumb.label }}</li>
      </template>
    </ol>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

// Legacy interface — exported for Topbar.vue / AppShell.vue backward compatibility
export interface BreadcrumbItem {
  label: string
  path?: string
}

interface InternalCrumb {
  label: string
  to?: string
}

const props = withDefaults(
  defineProps<{
    /** @deprecated Übergib stattdessen 'items' oder lass Auto-Derive laufen */
    crumbs?: BreadcrumbItem[]
    /** Explizite Liste — überschreibt Auto-Derive aus route.matched */
    items?: InternalCrumb[]
  }>(),
  { crumbs: () => [], items: undefined },
)

const route = useRoute()
const { t, te } = useI18n()

/** Auto-derived crumbs from route.matched using nav.* i18n keys */
const derivedCrumbs = computed<InternalCrumb[]>(() =>
  route.matched
    .filter((r) => r.name !== undefined)
    .map((r) => {
      const name = String(r.name!)
      const key = `nav.${name}`
      return { label: te(key) ? t(key) : name, to: r.path }
    }),
)

/** Final crumb list: items > crumbs (legacy) > auto-derive */
const resolvedCrumbs = computed<InternalCrumb[]>(() => {
  if (props.items) return props.items
  if (props.crumbs && props.crumbs.length > 0) {
    return props.crumbs.map((c) => ({ label: c.label, to: c.path }))
  }
  return derivedCrumbs.value
})
</script>

<style scoped>
.breadcrumbs {
  display: flex;
  align-items: center;
  font-size: 14px;
  color: var(--text-secondary);
}

.breadcrumbs__list {
  display: flex;
  align-items: center;
  gap: 6px;
  list-style: none;
  margin: 0;
  padding: 0;
}

.breadcrumbs__sep {
  color: var(--text-quaternary);
  font-weight: 400;
}

.breadcrumbs__item {
  color: var(--text-secondary);
  font-weight: 500;
}

.breadcrumbs__item--last {
  color: var(--text-primary);
  font-weight: 600;
}
</style>
