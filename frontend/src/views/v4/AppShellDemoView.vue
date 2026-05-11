<!--
  AppShellDemoView — lokale Verifikations-View fuer Slice B.
  Wird in Slice F in den Router eingebunden (aktuell kein Router-Eintrag).
-->
<template>
  <AppShell :breadcrumbs="crumbs" :notification-badge="3">
    <PageHeader
      title="Dashboard"
      subtitle="Willkommen bei Agora v4 Shell Demo"
    >
      <template #right>
        <button style="padding: 0 14px; height: 36px; border-radius: 8px; background: var(--accent); color: #fff; border: 0; font-size: 14px; font-weight: 600; cursor: pointer;">
          Neue Simulation
        </button>
      </template>
    </PageHeader>

    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px;">
      <div
        v-for="card in demoCards"
        :key="card.title"
        style="background: var(--surface-base, #fff); border-radius: 14px; padding: 22px;
               box-shadow: 0 0 0 1px var(--hairline), 0 1px 2px rgba(0,0,0,0.03);"
      >
        <h2 style="margin: 0 0 8px; font-size: 17px; font-weight: 600; letter-spacing: -0.005em;">
          {{ card.title }}
        </h2>
        <p style="margin: 0; font-size: 13px; color: var(--text-secondary);">
          {{ card.body }}
        </p>
      </div>
    </div>

    <!-- Inspector demo trigger -->
    <button
      style="margin-top: 24px; padding: 0 14px; height: 36px; border-radius: 8px; border: 1px solid var(--hairline); background: transparent; font-size: 14px; cursor: pointer;"
      @click="shellStore.toggleInspector()"
    >
      {{ shellStore.inspectorOpen ? 'Inspector schliessen' : 'Inspector oeffnen' }}
    </button>

    <template #inspector>
      <div style="padding: 20px;">
        <h3 style="margin: 0 0 12px; font-size: 15px; font-weight: 600;">Inspector</h3>
        <p style="font-size: 13px; color: var(--text-secondary);">Slice-B-Demo-Inspector. Slice F verdrahtet echten Inhalt.</p>
      </div>
    </template>
  </AppShell>
</template>

<script setup lang="ts">
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import { useShellStore } from '@/stores/shell'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'

const shellStore = useShellStore()

const crumbs: BreadcrumbItem[] = [
  { label: 'Agora' },
  { label: 'Dashboard' },
]

const demoCards = [
  { title: 'Aktive Simulationen', body: '3 laufende Pipeline-Runs — Details im Runs-Dashboard.' },
  { title: 'Letzte Reports', body: 'Zuletzt generiert: Klimaschutz-Debatte 2026-05-11.' },
  { title: 'Systemstatus', body: 'Alle Services gruen. Neo4j, Ollama, OASIS erreichbar.' },
]
</script>
