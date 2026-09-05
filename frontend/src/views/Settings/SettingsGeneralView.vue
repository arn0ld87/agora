<script setup lang="ts">
/**
 * SettingsGeneralView — Globale Workspace-Einstellungen.
 *
 * Phase-1 Konsolidierung (frontend-next): EIN Modell-Picker als einzige
 * Selektions-UI. Die Auswahl geht durch `useEffectiveModelSelection`, das
 * `routing/defaults.global` UND `active-config` im Gleichschritt schreibt
 * (Kanon: PHASE-1-DIVERGENZ.md). Die frühere separate „Active LLM Config“-
 * Sektion (eigene Provider/Modell-Dropdowns → active-config) wurde entfernt —
 * sie war die zweite, divergierende Server-Senke.
 *
 * Bewusst KEIN Override-Flow auf Stage-Ebene — dafür ist
 * StepModelOverrideChip zuständig. Hier geht es nur um den Workspace-Default.
 */
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import AiModelPicker from '@/components/v4/forms/AiModelPicker.vue'
import SettingsSectionPanel from '@/components/v4/forms/SettingsSectionPanel.vue'
import LlmProfileManager from '@/components/v4/forms/LlmProfileManager.vue'
import { useEffectiveModelSelection } from '@/composables/useEffectiveModelSelection'
import type { AiModelRef } from '@/contracts/aiModelRef'
import { GENERAL_SETTINGS_SECTIONS } from './settingsSections'

const { t } = useI18n()

const BREADCRUMBS = [
  { label: 'Settings', to: { name: 'SettingsGeneral' } },
  { label: 'General' },
]

const effectiveModel = useEffectiveModelSelection()

// Initialer Wert aus dem Kanon (routing/defaults.global via Adapter).
const selectedModel = ref<AiModelRef | null>(effectiveModel.effectiveRef.value)

onMounted(async () => {
  try {
    await effectiveModel.ensureLoaded()
    selectedModel.value = effectiveModel.effectiveRef.value
  } catch {
    /* Defaults bleiben leer — Picker zeigt nichts gewaehltes */
  }
})

async function setWorkspaceDefault(aiRef: AiModelRef | null): Promise<void> {
  if (!aiRef) return
  // Kanonischer Schreibpfad: routing/defaults.global + active-config im Gleichschritt.
  await effectiveModel.setGlobalSelection(aiRef)
}
</script>

<template>
  <AppShell :breadcrumbs="BREADCRUMBS">
    <PageHeader
      :title="t('settings.v4.general.title')"
      :subtitle="t('settings.v4.general.subtitle')"
    />

    <LlmProfileManager style="margin-bottom: 16px;" />
    <section class="settings-general__model-picker">
      <label for="settings-general-model-picker">{{ t('settings.v4.general.workspaceDefaultModel') }}</label>
      <AiModelPicker
        id="settings-general-model-picker"
        v-model="selectedModel"
        mode="chat"
        :allow-workspace-default="true"
        @update:model-value="setWorkspaceDefault"
      />
    </section>

    <SettingsSectionPanel :allowed-sections="GENERAL_SETTINGS_SECTIONS" />
  </AppShell>
</template>

<style scoped>
.settings-general__model-picker {
  display: grid;
  gap: 8px;
  min-width: 0;
  margin-bottom: 16px;
}
</style>
