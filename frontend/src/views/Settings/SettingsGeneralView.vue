<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import AiModelPicker from '@/components/v4/forms/AiModelPicker.vue'
import SettingsSectionPanel from '@/components/v4/forms/SettingsSectionPanel.vue'
import LlmProfileManager from '@/components/v4/forms/LlmProfileManager.vue'
import type { AiModelRef } from '@/contracts/aiModelRef'

const { t } = useI18n()

const BREADCRUMBS = [
  { label: 'Settings', to: { name: 'SettingsGeneral' } },
  { label: 'General' },
]

// .env-Sektionen, die das Laufzeit-Verhalten der Agora-App selbst beschreiben.
// Externe Systeme (Neo4j, Embedding, OASIS, ...) gehoeren in den
// Integrations-Tab und werden dort gerendert.
const ALLOWED_SECTIONS = ['llm', 'logging', 'locale', 'ui', 'event_bus', 'security'] as const
const selectedModel = ref<AiModelRef | null>(null)
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
    <section class="settings-general__model-picker">
      <label for="settings-general-model-picker">{{ t('aiModelPicker.label') }}</label>
      <AiModelPicker id="settings-general-model-picker" v-model="selectedModel" />
    </section>
    <SettingsSectionPanel :allowed-sections="ALLOWED_SECTIONS" />
  </AppShell>
</template>
