<script setup lang="ts">
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import Card from '@/components/v4/forms/Card.vue'

const BREADCRUMBS = [
  { label: 'Settings', to: { name: 'SettingsGeneral' } },
  { label: 'Integrations' },
]
</script>

<template>
  <AppShell :breadcrumbs="BREADCRUMBS">
    <PageHeader
      title="Integrations"
      subtitle="Externe Dienste und Datenquellen verbinden."
    />

    <Card title="Verbundene Dienste">
      <p class="stub-hint">
        Inhalt folgt in Slice G — aktuell verwaltet ueber den klassischen Tab in
        <RouterLink :to="{ name: 'Settings', query: { tab: 'integrations' } }">/settings?tab=integrations</RouterLink>.
      </p>
    </Card>
  </AppShell>
</template>

<style scoped>
.stub-hint {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
  margin: 0;
}
</style>
