<script setup lang="ts">
/** Pipeline — Platzhalter; Inhalt folgt in dieser Etappe (Bauplan §5). */
import { useI18n } from 'vue-i18n'
import SettingsGroup from '../SettingsGroup.vue'

const { t } = useI18n()
</script>

<template>
  <SettingsGroup :title="t('views.settingsWindow.placeholderTitle')">
    <p class="section-placeholder">{{ t('views.settingsWindow.placeholder') }}</p>
  </SettingsGroup>
</template>

<style scoped>
.section-placeholder {
  margin: 0;
  padding: 12px 0;
  font-size: 13.5px;
  color: var(--fg2);
}
</style>
