<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import ComingSoonCard from '@/components/v4/forms/ComingSoonCard.vue'

const { t } = useI18n()

const BREADCRUMBS = [
  { label: 'Settings', to: { name: 'SettingsGeneral' } },
  { label: 'API Keys' },
]
</script>

<template>
  <AppShell :breadcrumbs="BREADCRUMBS">
    <PageHeader
      :title="t('settings.v4.apiKeys.title')"
      :subtitle="t('settings.v4.apiKeys.subtitle')"
    />

    <ComingSoonCard
      :title="t('settings.v4.apiKeys.empty.title')"
      :description="t('settings.v4.apiKeys.empty.description')"
    />
  </AppShell>
</template>
