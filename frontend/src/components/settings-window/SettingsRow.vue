<script setup lang="ts">
/**
 * SettingsRow — eine Zeile in einer SettingsGroup: Beschriftung und Hilfetext
 * links, Bedienelement (Schalter, Auswahl, Button) im Standard-Slot rechts.
 * Mit `for` wird die Beschriftung ein echtes <label> zum Bedienelement.
 */
import { useId } from 'vue'

defineProps<{
  label: string
  hint?: string
  /** `id` des Bedienelements im Slot; macht die Beschriftung zum <label>. */
  for?: string
}>()

const hintId = useId()
</script>

<template>
  <div class="settings-row">
    <div class="settings-row__text">
      <label v-if="$props.for" class="settings-row__label" :for="$props.for">{{ label }}</label>
      <span v-else class="settings-row__label">{{ label }}</span>
      <span v-if="hint" :id="hintId" class="settings-row__hint">{{ hint }}</span>
    </div>
    <div class="settings-row__control">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.settings-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: center;
  padding: 11px 0;
  border-top: 1px solid var(--line);
  font-size: 13.5px;
}

.settings-row:first-child {
  border-top: 0;
}

.settings-row__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.settings-row__label {
  color: var(--fg);
  overflow-wrap: anywhere;
}

.settings-row__hint {
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--fg3);
}

.settings-row__control {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  min-width: 0;
}

@media (max-width: 767px) {
  .settings-row {
    grid-template-columns: minmax(0, 1fr);
    align-items: start;
  }

  .settings-row__control {
    justify-content: flex-start;
  }
}
</style>
