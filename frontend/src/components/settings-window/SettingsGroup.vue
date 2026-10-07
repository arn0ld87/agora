<script setup lang="ts">
/**
 * SettingsGroup — Gruppentitel plus Karte für die Zeilen eines Abschnitts
 * (Entwurf AgoraEinstellungen: `--s1`-Fläche, Radius 12). Die Zeilen kommen
 * als `SettingsRow` in den Standard-Slot.
 */
import { useId } from 'vue'

defineProps<{
  title: string
  description?: string
}>()

const titleId = useId()
</script>

<template>
  <section class="settings-group" :aria-labelledby="titleId">
    <h4 :id="titleId" class="settings-group__title">{{ title }}</h4>
    <p v-if="description" class="settings-group__description">{{ description }}</p>
    <div class="settings-group__card">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.settings-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.settings-group__title {
  margin: 0;
  padding: 0 4px;
  font-size: 13px;
  font-weight: 650;
  color: var(--fg2);
}

.settings-group__description {
  margin: 0;
  padding: 0 4px;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--fg3);
}

.settings-group__card {
  background: var(--s1);
  border-radius: var(--ag-r-12);
  padding: 2px 16px;
}
</style>
