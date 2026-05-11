/**
 * DashboardView — AppShell-Wrapper fuer das Dashboard (Slice F, Design-v4).
 *
 * Bettet den Placeholder-Inhalt ein. Vollstaendige Home-Inhalt-Migration
 * erfolgt in Slice H, wenn Home.vue in Einzelkomponenten aufgeteilt wird.
 */
<script setup lang="ts">
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import Card from '@/components/v4/forms/Card.vue'

const BREADCRUMBS = [{ label: 'Dashboard' }]
</script>

<template>
  <AppShell :breadcrumbs="BREADCRUMBS">
    <PageHeader
      title="Dashboard"
      subtitle="Uebersicht ueber aktive Projekte, Runs und Aktivitaet."
    />

    <Card title="Workspace-Uebersicht">
      <p class="stub-hint">
        Dashboard-Inhalt folgt in Slice H — die vollstaendige Home.vue-Migration
        in AppShell-Komponenten. Die klassische Startseite ist weiterhin unter
        <RouterLink to="/">/ (Landing)</RouterLink> erreichbar.
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
