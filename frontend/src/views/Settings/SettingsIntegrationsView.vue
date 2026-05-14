<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import SettingsSectionPanel from '@/components/v4/forms/SettingsSectionPanel.vue'

const { t } = useI18n()

const BREADCRUMBS = [
  { label: 'Settings', to: { name: 'SettingsGeneral' } },
  { label: 'Integrations' },
]

// Externe Systeme — Neo4j, Embedding-Provider, Ontology-LLM, Hybrid-Search,
// Agent-Tools, WebTools und OASIS-Runner.
const ALLOWED_SECTIONS = [
  'neo4j',
  'embedding',
  'ontology',
  'hybrid_search',
  'agent_tools',
  'webtools',
  'oasis',
] as const
</script>

<template>
  <AppShell :breadcrumbs="BREADCRUMBS">
    <PageHeader
      :title="t('settings.v4.integrations.title')"
      :subtitle="t('settings.v4.integrations.subtitle')"
    />

    <SettingsSectionPanel :allowed-sections="ALLOWED_SECTIONS" />
  </AppShell>
</template>
