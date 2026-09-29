<script setup lang="ts">
/**
 * SettingsOverlay — reiner Layout-Wrapper fuer alle `/settings/*`-Seiten.
 *
 * Fix #1713 (Befund 7, Doppelnavigation): trug bis hierhin eine eigene
 * Sektionsliste mit eigenem <h1> und "Zurueck"-Button — eine zweite,
 * parallele Navigationsebene neben der Sidebar-Gruppe „Einstellungen”
 * (Sidebar.vue), die dieselben Routen bereits verlinkte. Das eigene <h1>
 * kollidierte zusaetzlich mit dem <h1> aus PageHeader, das jede
 * Settings-View ohnehin schon setzt.
 *
 * Die Sidebar-Gruppe ist jetzt die einzige Navigationsebene fuer
 * Einstellungen (inkl. LLM-Routing und Audit-Logs, siehe Sidebar.vue);
 * diese Komponente bleibt nur noch als benannter Layout-Slot bestehen,
 * damit bestehende Views sie unveraendert einbinden koennen.
 */
import { SettingsOverlayTestId } from '@/contracts/testIds'
</script>

<template>
  <div class="settings-overlay" :data-testid="SettingsOverlayTestId.root">
    <slot />
  </div>
</template>

<style scoped>
.settings-overlay {
  display: flex;
  flex-direction: column;
  gap: var(--sp-5);
}
</style>
