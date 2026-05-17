<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import SettingsSectionPanel from '@/components/v4/forms/SettingsSectionPanel.vue'
import LlmProfileManager from '@/components/v4/forms/LlmProfileManager.vue'

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

    <!-- P5.3-Fix: LlmProviderCard entfernt — Funktionalität ist in /settings/llm-providers
         konsolidiert (kanonische Provider/Modell-Auswahl via ModelPicker). -->
    <LlmProfileManager style="margin-bottom: 16px;" />
    <SettingsSectionPanel :allowed-sections="ALLOWED_SECTIONS" />
  </AppShell>
</template>
