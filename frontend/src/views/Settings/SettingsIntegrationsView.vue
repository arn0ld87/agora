<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import SettingsSectionPanel from '@/components/v4/forms/SettingsSectionPanel.vue'
import { INTEGRATION_SETTINGS_SECTIONS } from './settingsSections'

const { t } = useI18n()

const BREADCRUMBS = computed(() => [
  { label: t('common.settings'), to: { name: 'SettingsGeneral' } },
  { label: t('sidebar.settings.integrations') },
])

</script>

<template>
  <AppShell :breadcrumbs="BREADCRUMBS">
    <PageHeader
      :title="t('settings.v4.integrations.title')"
      :subtitle="t('settings.v4.integrations.subtitle')"
    />

    <SettingsSectionPanel :allowed-sections="INTEGRATION_SETTINGS_SECTIONS" />
  </AppShell>
</template>
