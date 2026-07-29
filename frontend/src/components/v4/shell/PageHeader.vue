<template>
  <div class="page-header">
    <div class="page-header__text">
      <h1 class="page-header__title">{{ title }}</h1>
      <p v-if="subtitle" class="page-header__subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.right" class="page-header__right">
      <slot name="right" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  subtitle?: string
}>()
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  margin-bottom: 22px;
  gap: 16px;
}

.page-header__text {
  flex: 1;
  min-width: 0;
}

.page-header__title {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.018em;
  color: var(--text-primary);
  font-family: var(--font-sans);
}

.page-header__subtitle {
  margin: 4px 0 0;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 400;
}

.page-header__right {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}
</style>
