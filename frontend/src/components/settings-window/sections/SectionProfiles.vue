<script setup lang="ts">
/**
 * Profile (Bauplan §5) — ersetzt `settings/llm-routing` und den
 * `LlmProfileManager` aus „Allgemein“.
 *
 * Ein `LlmProfile` ist im Bestand genau EIN Modell (Anbieter, Basisadresse,
 * Modellname, Standardmarkierung), kein Profil mit vier Stufen. Die Zuordnung
 * je Stufe liegt in den Routing-Standards und heißt hier ehrlich
 * „Standardmodell je Stufe“.
 */
import { useI18n } from 'vue-i18n'
import LlmProfileManager from '@/components/v4/forms/LlmProfileManager.vue'
import SettingsSectionPanel from '@/components/v4/forms/SettingsSectionPanel.vue'
import LlmRoutingView from '@/views/Settings/LlmRoutingView.vue'
import { PROFILE_SETTINGS_SECTIONS } from '@/views/Settings/settingsSections'
import SettingsGroup from '../SettingsGroup.vue'

const { t } = useI18n()
</script>

<template>
  <div class="section-profiles">
    <SettingsGroup
      :title="t('views.settingsWindow.profiles.modelsTitle')"
      :description="t('views.settingsWindow.profiles.modelsDescription')"
    >
      <LlmProfileManager />
    </SettingsGroup>

    <SettingsGroup
      :title="t('views.settingsWindow.profiles.stagesTitle')"
      :description="t('views.settingsWindow.profiles.stagesDescription')"
    >
      <LlmRoutingView embedded />
    </SettingsGroup>

    <SettingsGroup :title="t('views.settingsWindow.profiles.valuesTitle')">
      <SettingsSectionPanel :allowed-sections="PROFILE_SETTINGS_SECTIONS" />
    </SettingsGroup>
  </div>
</template>

<style scoped>
.section-profiles {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
</style>
