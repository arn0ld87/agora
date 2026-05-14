<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import ComingSoonCard from '@/components/v4/forms/ComingSoonCard.vue'

const { t } = useI18n()

const BREADCRUMBS = [
  { label: 'Settings', to: { name: 'SettingsGeneral' } },
  { label: 'Users & Teams' },
]
</script>

<template>
  <AppShell :breadcrumbs="BREADCRUMBS">
    <PageHeader
      :title="t('settings.v4.usersTeams.title')"
      :subtitle="t('settings.v4.usersTeams.subtitle')"
    />

    <ComingSoonCard
      :title="t('settings.v4.usersTeams.empty.title')"
      :description="t('settings.v4.usersTeams.empty.description')"
    />
  </AppShell>
</template>
