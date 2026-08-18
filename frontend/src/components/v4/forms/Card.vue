<script setup lang="ts">
withDefaults(defineProps<{
  title?: string
  subtitle?: string
  pad?: number
}>(), {
  pad: 22,
})
</script>

<template>
  <div class="v4-card" :style="{ padding: `${pad}px` }">
    <div
      v-if="title || $slots['right']"
      class="v4-card__header"
      :class="{ 'v4-card__header--with-subtitle': subtitle }"
    >
      <div class="v4-card__header-text">
        <h2 v-if="title" class="v4-card__title">{{ title }}</h2>
        <div v-if="subtitle" class="v4-card__subtitle">{{ subtitle }}</div>
      </div>
      <div v-if="$slots['right']" class="v4-card__right">
        <slot name="right" />
      </div>
    </div>

    <div class="v4-card__body">
      <slot />
    </div>

    <div v-if="$slots['footer']" class="v4-card__footer">
      <slot name="footer" />
    </div>
  </div>
</template>

<style scoped>
.v4-card {
  background: var(--surface-elevated);
  border-radius: 14px;
  box-shadow: 0 0 0 1px var(--hairline), 0 1px 1px rgba(0, 0, 0, 0.02);
}

.v4-card__header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

/* Wenn subtitle vorhanden: etwas weniger margin-bottom */
.v4-card__header--with-subtitle {
  margin-bottom: 14px;
}

.v4-card__header-text {
  flex: 1;
  min-width: 0;
}

.v4-card__title {
  margin: 0;
  font-family: var(--font-sans);
  font-size: 17px;
  font-weight: 600;
  letter-spacing: -0.005em;
  color: var(--text-primary);
  line-height: 1.3;
}

.v4-card__subtitle {
  margin-top: 4px;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.v4-card__right {
  flex: none;
}

.v4-card__body {
  /* body hat kein extra spacing — liegt direkt im card-padding */
}

.v4-card__footer {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--separator);
}
</style>
