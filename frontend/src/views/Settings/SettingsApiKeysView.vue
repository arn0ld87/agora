<script setup lang="ts">
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import Card from '@/components/v4/forms/Card.vue'

const BREADCRUMBS = [
  { label: 'Settings', to: { name: 'SettingsGeneral' } },
  { label: 'API Keys' },
]
</script>

<template>
  <AppShell :breadcrumbs="BREADCRUMBS">
    <PageHeader
      title="API Keys"
      subtitle="API-Zugaenge erstellen und verwalten."
    />

    <Card title="Aktive Schlussel">
      <p class="stub-hint">
        Inhalt folgt in Slice G — aktuell verwaltet ueber den klassischen Tab in
        <RouterLink :to="{ name: 'Settings', query: { tab: 'api-keys' } }">/settings?tab=api-keys</RouterLink>.
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
