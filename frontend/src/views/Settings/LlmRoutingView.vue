<script setup lang="ts">
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import StickyActionBar from '@/components/v4/forms/StickyActionBar.vue'
import GlobalDefaultCard from './llmRouting/GlobalDefaultCard.vue'
import ActiveSnapshotsCard from './llmRouting/ActiveSnapshotsCard.vue'
import StageOverridesCard from './llmRouting/StageOverridesCard.vue'
import CustomModelCard from './llmRouting/CustomModelCard.vue'

const BREADCRUMBS = [
  { label: 'Settings', to: { name: 'SettingsGeneral' } },
  { label: 'LLM Routing' },
]
</script>

<template>
  <AppShell :breadcrumbs="BREADCRUMBS">
    <PageHeader
      title="LLM Routing"
      subtitle="Provider, Modellwahl und Stage-Routing pro Run konfigurieren."
    />

    <!-- Zeile 1: Global Default + Aktive Snapshots -->
    <div class="llmr-grid">
      <GlobalDefaultCard />
      <ActiveSnapshotsCard />
    </div>

    <!-- Zeile 2: Stage Overrides + Custom Model -->
    <div class="llmr-grid llmr-grid--lower">
      <StageOverridesCard />
      <CustomModelCard />
    </div>

    <!-- Sticky Action Bar -->
    <StickyActionBar>
      <template #right>
        <button class="llmr-btn llmr-btn--secondary" type="button">Zurücksetzen</button>
        <button class="llmr-btn llmr-btn--primary" type="button">Speichern</button>
      </template>
    </StickyActionBar>
  </AppShell>
</template>

<style scoped>
.llmr-grid {
  display: grid;
  grid-template-columns: 1.05fr 1fr;
  gap: 20px;
}

.llmr-grid--lower {
  margin-top: 20px;
}

/* Global Buttons */
.llmr-btn {
  display: inline-flex;
  align-items: center;
  height: 36px;
  padding: 0 16px;
  border-radius: 8px;
  font-family: var(--font-sans);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 120ms ease, border-color 120ms ease;
}

.llmr-btn--primary {
  background: var(--accent, #0a84ff);
  color: #fff;
  border-color: var(--accent, #0a84ff);
}

.llmr-btn--primary:hover {
  background: var(--accent-hover, #006edb);
  border-color: var(--accent-hover, #006edb);
}

.llmr-btn--secondary {
  background: var(--surface-elevated, #fff);
  color: var(--text-primary);
  border-color: var(--hairline);
}

.llmr-btn--secondary:hover {
  background: var(--surface-inset, #f2f2f7);
}
</style>
