<script setup lang="ts">
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import Card from '@/components/v4/forms/Card.vue'

const BREADCRUMBS = [
  { label: 'Settings', to: { name: 'SettingsGeneral' } },
  { label: 'Users & Teams' },
]
</script>

<template>
  <AppShell :breadcrumbs="BREADCRUMBS">
    <PageHeader
      title="Users & Teams"
      subtitle="Nutzer verwalten und Teamzugaenge konfigurieren."
    />

    <Card title="Teammitglieder">
      <p class="stub-hint">
        Inhalt folgt in Slice G — aktuell verwaltet ueber den klassischen Tab in
        <RouterLink :to="{ name: 'Settings', query: { tab: 'users' } }">/settings?tab=users</RouterLink>.
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
