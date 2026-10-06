<script setup lang="ts">
/**
 * Pipeline — Ontologie, Hybridsuche, Agentenwerkzeuge, Web-Werkzeuge, OASIS:
 * der Inhalt von `/settings/integrations` ohne `budget` (eigener Abschnitt).
 * Der Abschnittsname steht im Fensterkopf, hier folgt kein eigenes `<h1>`.
 */
import SettingsSectionPanel from '@/components/v4/forms/SettingsSectionPanel.vue'
import { PIPELINE_SETTINGS_SECTIONS } from '../pipeline/pipelineSections'
</script>

<template>
  <SettingsSectionPanel :allowed-sections="PIPELINE_SETTINGS_SECTIONS" />
</template>
