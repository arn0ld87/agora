<template>
  <nav class="breadcrumbs" aria-label="Breadcrumb">
    <template v-for="(crumb, index) in crumbs" :key="crumb.path ?? crumb.label">
      <span
        v-if="index > 0"
        class="breadcrumbs__sep"
        aria-hidden="true"
      >/</span>
      <span
        class="breadcrumbs__item"
        :class="{ 'breadcrumbs__item--last': index === crumbs.length - 1 }"
      >{{ crumb.label }}</span>
    </template>
  </nav>
</template>

<script setup lang="ts">
export interface BreadcrumbItem {
  label: string
  path?: string
}

withDefaults(
  defineProps<{
    crumbs?: BreadcrumbItem[]
  }>(),
  { crumbs: () => [] },
)
</script>

<style scoped>
.breadcrumbs {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--text-secondary);
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
