<script setup lang="ts">
/**
 * SettingsGeneralView — Globale Workspace-Einstellungen.
 *
 * Slice 5.4: Pilot-Abschluss der AiModelPicker-Migration.
 *  - AiModelPicker-Update wird an useLlmRoutingDefaultsStore.setGlobalDefault
 *    durchgereicht (Adapter Uebersetzung AiModelRef -> LlmRoute).
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
import Button from '@/components/v4/forms/Button.vue'
import SettingsSectionPanel from '@/components/v4/forms/SettingsSectionPanel.vue'
import LlmProfileManager from '@/components/v4/forms/LlmProfileManager.vue'
import { useLlmRoutingDefaultsStore } from '@/store/aiModels'
import { useAiModelRefAdapter } from '@/composables/useAiModelRefAdapter'
import type { AiModelRef } from '@/contracts/aiModelRef'
import {
  getActiveLlmConfig,
  listLlmProviders,
  listProviderModels,
  setActiveLlmConfig,
} from '@/api/llmRouting'
import { GENERAL_SETTINGS_SECTIONS } from './settingsSections'

const { t } = useI18n()

const BREADCRUMBS = [
  { label: 'Settings', to: { name: 'SettingsGeneral' } },
  { label: 'General' },
]

const defaultsStore = useLlmRoutingDefaultsStore()
const adapter = useAiModelRefAdapter()

// Initialer Wert aus dem Store (via Adapter: LlmRoute -> AiModelRef).
const selectedModel = ref<AiModelRef | null>(
  defaultsStore.globalDefault ? adapter.toAiModelRef(defaultsStore.globalDefault) : null,
)

const activeProviders = ref<Awaited<ReturnType<typeof listLlmProviders>>>([])
const activeModels = ref<Awaited<ReturnType<typeof listProviderModels>>>([])
const activeProviderId = ref('')
const activeModelId = ref('')
const activeLoadingProviders = ref(false)
const activeLoadingModels = ref(false)
const activeSaving = ref(false)
const activeError = ref('')
const activeFlash = ref('')

function messageFrom(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

async function loadActiveProviders(): Promise<void> {
  activeLoadingProviders.value = true
  activeError.value = ''
  try {
    activeProviders.value = await listLlmProviders()
  } catch (error) {
    activeError.value = messageFrom(error, t('settings.llmActive.errorLoadProviders'))
  } finally {
    activeLoadingProviders.value = false
  }
}

async function loadActiveModels(providerId: string): Promise<void> {
  if (!providerId) {
    activeModels.value = []
    return
  }

  activeLoadingModels.value = true
  try {
    activeModels.value = await listProviderModels(providerId)
  } catch (error) {
    activeModels.value = []
    activeError.value = messageFrom(error, t('settings.llmActive.errorLoadModels'))
  } finally {
    activeLoadingModels.value = false
  }
}

async function loadActiveSelection(): Promise<void> {
  try {
    const config = await getActiveLlmConfig()
    activeProviderId.value = config.provider_id ?? ''
    if (activeProviderId.value) {
      await loadActiveModels(activeProviderId.value)
    }
    activeModelId.value = config.model ?? ''
  } catch (error) {
    activeError.value = messageFrom(error, t('settings.llmActive.errorLoadActive'))
  }
}

async function changeActiveProvider(event: Event): Promise<void> {
  activeProviderId.value = (event.target as HTMLSelectElement).value
  activeModelId.value = ''
  activeFlash.value = ''
  activeError.value = ''
  await loadActiveModels(activeProviderId.value)
}

async function saveActiveSelection(): Promise<void> {
  if (!activeProviderId.value || !activeModelId.value) {
    activeError.value = t('settings.llmActive.errorSelectionMissing')
    return
  }

  activeSaving.value = true
  activeError.value = ''
  activeFlash.value = ''
  try {
    await setActiveLlmConfig({
      provider_id: activeProviderId.value,
      model: activeModelId.value,
    })
    activeFlash.value = t('settings.llmActive.flashSaved')
  } catch (error) {
    activeError.value = messageFrom(error, t('settings.llmActive.errorSaveFailed'))
  } finally {
    activeSaving.value = false
  }
}

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

onMounted(async () => {
  await loadActiveProviders()
  await loadActiveSelection()
})

async function setWorkspaceDefault(aiRef: AiModelRef | null): Promise<void> {
  if (!aiRef) return
  const llmRoute = adapter.toLlmRoute(aiRef)
  await defaultsStore.setGlobalDefault(llmRoute)
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

    <section
      class="settings-general__active"
      aria-labelledby="settings-active-title"
    >
      <header>
        <h2 id="settings-active-title">{{ t('settings.llmActive.title') }}</h2>
        <p>{{ t('settings.llmActive.subtitle') }}</p>
      </header>

      <div class="settings-general__active-fields">
        <label for="settings-active-provider">{{ t('settings.llmActive.providerLabel') }}</label>
        <select
          id="settings-active-provider"
          :value="activeProviderId"
          :disabled="activeLoadingProviders"
          @change="changeActiveProvider"
        >
          <option value="" disabled>
            {{ activeLoadingProviders ? t('settings.llmActive.providerLoading') : t('settings.llmActive.providerPlaceholder') }}
          </option>
          <option
            v-for="provider in activeProviders"
            :key="provider.id"
            :value="provider.id"
          >
            {{ provider.label || provider.id }}
          </option>
        </select>

        <label for="settings-active-model">{{ t('settings.llmActive.modelLabel') }}</label>
        <select
          id="settings-active-model"
          v-model="activeModelId"
          :disabled="!activeProviderId || activeLoadingModels"
        >
          <option value="" disabled>
            {{
              !activeProviderId
                ? t('settings.llmActive.modelNeedsProvider')
                : activeLoadingModels
                  ? t('settings.llmActive.modelLoading')
                  : activeModels.length
                    ? t('settings.llmActive.modelPlaceholder')
                    : t('settings.llmActive.modelEmpty')
            }}
          </option>
          <option
            v-for="model in activeModels"
            :key="model.id"
            :value="model.id"
          >
            {{ model.id }}{{ model.label && model.label !== model.id ? ` — ${model.label}` : '' }}
          </option>
        </select>
      </div>

      <p
        v-if="activeFlash"
        class="settings-general__active-feedback"
        role="status"
        aria-live="polite"
      >
        {{ activeFlash }}
      </p>
      <p
        v-if="activeError"
        class="settings-general__active-feedback settings-general__active-feedback--error"
        role="alert"
      >
        {{ activeError }}
      </p>

      <Button
        class="settings-general__active-save"
        variant="accent"
        :loading="activeSaving"
        :disabled="!activeProviderId || !activeModelId || activeSaving"
        @click="saveActiveSelection"
      >
        {{ t('settings.llmActive.save') }}
      </Button>
    </section>

    <SettingsSectionPanel :allowed-sections="GENERAL_SETTINGS_SECTIONS" />
  </AppShell>
</template>

<style scoped>
.settings-general__active {
  display: grid;
  gap: 16px;
  min-width: 0;
  margin-bottom: 16px;
  padding: 20px;
  border: 1px solid var(--hairline);
  border-radius: 12px;
  background: var(--surface-elevated);
}

.settings-general__active header,
.settings-general__active header p {
  margin: 0;
}

.settings-general__active header {
  display: grid;
  gap: 6px;
}

.settings-general__active-fields {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 2fr);
  gap: 10px 16px;
  align-items: center;
  min-width: 0;
}

.settings-general__active-fields select {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid var(--hairline);
  border-radius: 8px;
  color: var(--text-primary);
  background: var(--surface-elevated);
}

.settings-general__active-fields select:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.settings-general__active-feedback {
  margin: 0;
}

.settings-general__active-feedback--error {
  color: var(--danger);
}

.settings-general__active-save {
  justify-self: end;
}

@media (max-width: 480px) {
  .settings-general__active {
    padding: 16px;
  }

  .settings-general__active-fields {
    grid-template-columns: minmax(0, 1fr);
  }

  .settings-general__active-save {
    justify-self: stretch;
  }
}
</style>
