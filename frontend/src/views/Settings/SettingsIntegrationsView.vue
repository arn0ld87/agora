<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import SettingsOverlay from '@/components/v4/forms/SettingsOverlay.vue'
import SettingsSectionPanel from '@/components/v4/forms/SettingsSectionPanel.vue'
import { INTEGRATION_SETTINGS_SECTIONS } from './settingsSections'

const { t } = useI18n()
</script>

<template>
  <AppShell>
    <SettingsOverlay>
      <PageHeader
        :title="t('settings.v4.integrations.title')"
        :subtitle="t('settings.v4.integrations.subtitle')"
      />

      <SettingsSectionPanel :allowed-sections="INTEGRATION_SETTINGS_SECTIONS" />
    </SettingsOverlay>
  </AppShell>
</template>
