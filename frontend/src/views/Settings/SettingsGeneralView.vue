<script setup lang="ts">
/**
 * SettingsGeneralView — Globale Workspace-Einstellungen.
 *
 * Slice 5.4: Pilot-Abschluss der AiModelPicker-Migration.
 *  - AiModelPicker-Update wird an useLlmRoutingDefaultsStore.setGlobalDefault
 *    durchgereicht (Adapter Uebersetzung AiModelRef -> StageLLMRoute).
 *  - Initialer Wert kommt aus defaultsStore.globalDefault (via Adapter).
 *  - i18n-Key 'settings.v4.general.workspaceDefaultModel' ersetzt das
 *    generische aiModelPicker.label und macht die Funktion klar.
 *
 * Bewusst KEIN Override-Flow auf Stage-Ebene — dafuer ist
 * StepModelOverrideChip zustaendig. Hier geht es nur um den
 * Workspace-Default.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import AiModelPicker from '@/components/v4/forms/AiModelPicker.vue'
import SettingsSectionPanel from '@/components/v4/forms/SettingsSectionPanel.vue'
import LlmProfileManager from '@/components/v4/forms/LlmProfileManager.vue'
// legacy-model-picker-allow: 5.4 Workspace-Default liest v3-Routing-Default; wird in 5.5 durch useActiveModelStore ersetzt
import { useLlmRoutingDefaultsStore } from '@/store/llmRoutingDefaults'
import { useAiModelRefAdapter } from '@/composables/useAiModelRefAdapter'
import type { AiModelRef } from '@/contracts/aiModelRef'

const { t } = useI18n()

const BREADCRUMBS = [
  { label: 'Settings', to: { name: 'SettingsGeneral' } },
  { label: 'General' },
]

// .env-Sektionen, die das Laufzeit-Verhalten der Agora-App selbst beschreiben.
// Externe Systeme (Neo4j, Embedding, OASIS, ...) gehoeren in den
// Integrations-Tab und werden dort gerendert.
const ALLOWED_SECTIONS = ['llm', 'logging', 'locale', 'ui', 'event_bus', 'security'] as const

const defaultsStore = useLlmRoutingDefaultsStore()
const adapter = useAiModelRefAdapter()

// Initialer Wert aus dem Store (via Adapter: StageLLMRoute -> AiModelRef).
const selectedModel = ref<AiModelRef | null>(
  defaultsStore.globalDefault ? adapter.toAiModelRef(defaultsStore.globalDefault) : null,
)

onMounted(async () => {
  try {
    await defaultsStore.load()
    if (defaultsStore.globalDefault) {
      selectedModel.value = adapter.toAiModelRef(defaultsStore.globalDefault)
    }
  } catch {
    /* Defaults bleiben leer — Picker zeigt nichts gewaehltes */
  }
})

async function setWorkspaceDefault(aiRef: AiModelRef | null): Promise<void> {
  if (!aiRef) return
  const stageLlmRoute = adapter.toStageLlmRoute(aiRef)
  await defaultsStore.setGlobalDefault(stageLlmRoute)
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
    <SettingsSectionPanel :allowed-sections="ALLOWED_SECTIONS" />
  </AppShell>
</template>
