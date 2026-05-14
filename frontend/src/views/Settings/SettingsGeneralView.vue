<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import SettingsSectionPanel from '@/components/v4/forms/SettingsSectionPanel.vue'
import LlmProviderCard from '@/components/v4/forms/LlmProviderCard.vue'

const { t } = useI18n()

const BREADCRUMBS = [
  { label: 'Settings', to: { name: 'SettingsGeneral' } },
  { label: 'General' },
]

// .env-Sektionen, die das Laufzeit-Verhalten der Agora-App selbst beschreiben.
// Externe Systeme (Neo4j, Embedding, OASIS, ...) gehoeren in den
// Integrations-Tab und werden dort gerendert.
const ALLOWED_SECTIONS = ['llm', 'logging', 'locale', 'ui', 'event_bus', 'security'] as const
</script>

<template>
  <AppShell :breadcrumbs="BREADCRUMBS">
    <PageHeader
      :title="t('settings.v4.general.title')"
      :subtitle="t('settings.v4.general.subtitle')"
    />

    <LlmProviderCard style="margin-bottom: 16px;" />
    <SettingsSectionPanel :allowed-sections="ALLOWED_SECTIONS" />
  </AppShell>
</template>
