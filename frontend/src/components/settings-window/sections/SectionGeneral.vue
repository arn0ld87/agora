<script setup lang="ts">
/**
 * Allgemein (Bauplan §5) — Sprache, Protokollstufe, Benachrichtigungen
 * (Settings-Abschnitte `logging`, `locale`, `event_bus`, `ui`, `security`)
 * und das Standardmodell des Workspace. Der Modell-Profilmanager und der
 * Abschnitt `llm` sind nach „Profile“ gewandert.
 *
 * Der Inhalt der bisherigen Ansicht `/settings/general` wird ohne eigenen
 * Seitenkopf eingebettet.
 */
import SettingsGeneralView from '@/views/Settings/SettingsGeneralView.vue'
</script>

<template>
  <SettingsGeneralView embedded />
</template>
