<script setup lang="ts">
/**
 * Aussehen — Farbschema, Dichte, Schriftgröße (#1799, Etappe 3).
 *
 * Bindet die Bestandsmechanismen an: useTheme (data-theme), useDensity
 * (data-density) und useFontSize (data-font-size). Alles lokal im Browser.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import SettingsGroup from '../SettingsGroup.vue'
import SettingsRow from '../SettingsRow.vue'
import SegmentedChoice from '../appearance/SegmentedChoice.vue'
import { useTheme, type ThemeChoice } from '@/composables/useTheme'
import { useDensity, type Density } from '@/composables/useDensity'
import { useFontSize, type FontSize } from '@/composables/settings-window/useFontSize'

const { t } = useI18n()
const { choice, setChoice } = useTheme()
const { density, setDensity } = useDensity()
const { fontSize, setFontSize } = useFontSize()

const themeOptions = computed(() => [
  { value: 'system' as ThemeChoice, label: t('views.settingsWindow.appearance.theme.system') },
  { value: 'light' as ThemeChoice, label: t('views.settingsWindow.appearance.theme.light') },
  { value: 'dark' as ThemeChoice, label: t('views.settingsWindow.appearance.theme.dark') },
])
const densityOptions = computed(() => [
  { value: 'comfortable' as Density, label: t('views.settingsWindow.appearance.density.comfortable') },
  { value: 'compact' as Density, label: t('views.settingsWindow.appearance.density.compact') },
])
const fontOptions = computed(() => [
  { value: 'small' as FontSize, label: t('views.settingsWindow.appearance.fontSize.small') },
  { value: 'normal' as FontSize, label: t('views.settingsWindow.appearance.fontSize.normal') },
  { value: 'large' as FontSize, label: t('views.settingsWindow.appearance.fontSize.large') },
])
</script>

<template>
  <div class="section-appearance">
    <SettingsGroup
      :title="t('views.settingsWindow.appearance.groupTheme')"
      :description="t('views.settingsWindow.appearance.local')"
    >
      <SettingsRow
        :label="t('views.settingsWindow.appearance.theme.label')"
        :hint="t('views.settingsWindow.appearance.theme.hint')"
      >
        <SegmentedChoice
          :model-value="choice"
          :options="themeOptions"
          :label="t('views.settingsWindow.appearance.theme.label')"
          @update:model-value="setChoice"
        />
      </SettingsRow>
    </SettingsGroup>

    <SettingsGroup :title="t('views.settingsWindow.appearance.groupText')">
      <SettingsRow
        :label="t('views.settingsWindow.appearance.density.label')"
        :hint="t('views.settingsWindow.appearance.density.hint')"
      >
        <SegmentedChoice
          :model-value="density"
          :options="densityOptions"
          :label="t('views.settingsWindow.appearance.density.label')"
          @update:model-value="setDensity"
        />
      </SettingsRow>
      <SettingsRow
        :label="t('views.settingsWindow.appearance.fontSize.label')"
        :hint="t('views.settingsWindow.appearance.fontSize.hint')"
      >
        <SegmentedChoice
          :model-value="fontSize"
          :options="fontOptions"
          :label="t('views.settingsWindow.appearance.fontSize.label')"
          @update:model-value="setFontSize"
        />
      </SettingsRow>
    </SettingsGroup>
  </div>
</template>

<style scoped>
.section-appearance {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
</style>
