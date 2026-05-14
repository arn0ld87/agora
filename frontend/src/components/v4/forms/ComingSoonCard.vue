<script setup lang="ts">
/**
 * Wieder verwendbarer "Coming Soon"-Empty-State (Slice G1).
 *
 * Ersetzt die nackten "Inhalt folgt in Slice G"-Stubs aus
 * frontend/src/views/Settings/Settings*View.vue durch eine ruhige,
 * markenkonforme Karte mit Icon, Titel, Beschreibung und optionalem
 * Verweis auf den klassischen Tab.
 */
import Card from './Card.vue'
import IconSpark from '@/components/v4/shell/icons/IconSpark.vue'

withDefaults(defineProps<{
  title: string
  description: string
  /** Optional: Routed-Link-Label fuer Fallback auf klassischen Tab. */
  fallbackLabel?: string
  /** Optional: Pfad oder Name-Object fuer Router-Link. */
  fallbackTo?: string | { name: string; query?: Record<string, string> }
}>(), {
  fallbackLabel: '',
  fallbackTo: '',
})
</script>

<template>
  <Card>
    <div class="v4-coming-soon">
      <div class="v4-coming-soon__icon" aria-hidden="true">
        <IconSpark />
      </div>
      <h3 class="v4-coming-soon__title">{{ title }}</h3>
      <p class="v4-coming-soon__desc">{{ description }}</p>
      <RouterLink
        v-if="fallbackLabel && fallbackTo"
        :to="fallbackTo"
        class="v4-coming-soon__link"
      >
        {{ fallbackLabel }}
      </RouterLink>
    </div>
  </Card>
</template>

<style scoped>
.v4-coming-soon {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 32px 16px;
  gap: 10px;
}
.v4-coming-soon__icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: var(--accent-tint-bg);
  color: var(--accent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.v4-coming-soon__icon :deep(svg) {
  width: 22px;
  height: 22px;
}
.v4-coming-soon__title {
  margin: 0;
  font-family: var(--font-sans);
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
}
.v4-coming-soon__desc {
  margin: 0;
  font-family: var(--font-sans);
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
  max-width: 36ch;
}
.v4-coming-soon__link {
  margin-top: 4px;
  font-size: 13px;
  color: var(--accent);
  text-decoration: none;
}
.v4-coming-soon__link:hover {
  text-decoration: underline;
}
</style>
