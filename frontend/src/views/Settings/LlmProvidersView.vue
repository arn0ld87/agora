<script setup lang="ts">
/**
 * LlmProvidersView — Workspace-weite LLM-Provider-Konfiguration.
 *
 * Pro Provider eine Karte mit:
 *   - Status-Badge (connected / missing / fallback)
 *   - Key-Eingabe (type=password) + optional Base-URL (für openai_compatible)
 *   - Buttons: Speichern, Test, Modelle laden, Trennen
 *   - Sichtbare Modellliste (Source: live/cached/fallback)
 *   - Inline Global-Default-Picker (Workspace-Default-Routing)
 *
 * Klartext-Keys verlassen niemals das Backend nach dem Speichern. Im Frontend
 * wird nur ``masked_value`` (sk-...abcd) angezeigt.
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import Card from '@/components/v4/forms/Card.vue'
import Badge from '@/components/v4/forms/Badge.vue'
import Input from '@/components/v4/forms/Input.vue'
import ModelPicker from '@/components/v4/forms/ModelPicker.vue'
import { useLlmProvidersStore } from '@/store/llmProviders'
import { useLlmRoutingDefaultsStore } from '@/store/llmRoutingDefaults'
import type { ProviderDescriptor, StageLLMRoute } from '@/contracts/llmRoutingContract'

const { t } = useI18n()

const providersStore = useLlmProvidersStore()
const defaultsStore = useLlmRoutingDefaultsStore()

const BREADCRUMBS = [
  { label: 'Settings', to: { name: 'SettingsGeneral' } },
  { label: t('settings.v4.llmProviders.title', 'LLM-Provider') },
]

interface DraftState {
  apiKey: string
  baseUrl: string
  testMessage: string | null
  testOk: boolean | null
}

const drafts = reactive<Record<string, DraftState>>({})

function ensureDraft(providerId: string): DraftState {
  if (!(providerId in drafts)) {
    drafts[providerId] = {
      apiKey: '',
      baseUrl: providersStore.entries[providerId]?.base_url || '',
      testMessage: null,
      testOk: null,
    }
  }
  return drafts[providerId]
}

function statusBadgeVariant(p: ProviderDescriptor): 'success' | 'neutral' | 'warning' {
  if (providersStore.hasKey(p.id)) return 'success'
  if (p.type === 'ollama_local') return 'neutral'
  return 'warning'
}

function statusLabel(p: ProviderDescriptor): string {
  if (providersStore.hasKey(p.id)) return t('settings.v4.llmProviders.status.connected', 'verbunden')
  if (p.type === 'ollama_local') return t('settings.v4.llmProviders.status.local', 'lokal')
  if (p.type === 'github_copilot') return t('settings.v4.llmProviders.status.cli', 'gh CLI')
  return t('settings.v4.llmProviders.status.missing', 'Key fehlt')
}

async function save(p: ProviderDescriptor): Promise<void> {
  const draft = ensureDraft(p.id)
  draft.testMessage = null
  draft.testOk = null
  if (!draft.apiKey.trim()) return
  try {
    await providersStore.saveKey(p.id, draft.apiKey.trim(), draft.baseUrl.trim() || undefined, {
      validate: true,
    })
    draft.apiKey = ''
    draft.testOk = true
    draft.testMessage = t('settings.v4.llmProviders.test.saved', 'Gespeichert.')
  } catch (err) {
    draft.testOk = false
    draft.testMessage = err instanceof Error ? err.message : String(err)
  }
}

async function runTest(p: ProviderDescriptor): Promise<void> {
  const draft = ensureDraft(p.id)
  draft.testMessage = null
  draft.testOk = null
  try {
    const result = await providersStore.testProvider(p.id, {
      api_key: draft.apiKey.trim() || undefined,
      base_url: draft.baseUrl.trim() || undefined,
    })
    draft.testOk = result.connectivity === 'ok'
    draft.testMessage = draft.testOk
      ? t('settings.v4.llmProviders.test.ok', { count: result.models_found ?? 0 })
      : t('settings.v4.llmProviders.test.failed')
  } catch (err) {
    draft.testOk = false
    draft.testMessage = err instanceof Error ? err.message : String(err)
  }
}

async function loadModels(p: ProviderDescriptor): Promise<void> {
  await providersStore.fetchModels(p.id, { force: true })
}

async function disconnect(p: ProviderDescriptor): Promise<void> {
  await providersStore.revokeKey(p.id)
  const draft = ensureDraft(p.id)
  draft.testMessage = null
  draft.testOk = null
}

const defaultRoute = computed<StageLLMRoute | null>(() => {
  const r = defaultsStore.globalDefault
  if (!r?.provider_id || !r?.model) return null
  return r
})

async function setDefault(route: StageLLMRoute | null): Promise<void> {
  if (!route) return
  await defaultsStore.setGlobalDefault(route)
}

onMounted(async () => {
  await providersStore.loadProviders()
  await defaultsStore.load()
})
</script>

<template>
  <AppShell>
    <PageHeader
      :title="t('settings.v4.llmProviders.title', 'LLM-Provider')"
      :subtitle="t('settings.v4.llmProviders.subtitle', 'Hinterlege API-Schlüssel, ziehe Modelle und wähle pro Schritt das passende Modell aus.')"
      :breadcrumbs="BREADCRUMBS"
    />

    <div class="llm-providers-grid">
      <Card
        :title="t('settings.v4.llmProviders.defaults.title', 'Workspace-Default')"
        :subtitle="t('settings.v4.llmProviders.defaults.subtitle', 'Wird automatisch beim Start eines neuen Runs für alle Schritte übernommen.')"
      >
        <div class="llm-default-row">
          <ModelPicker
            :model-value="defaultRoute"
            :placeholder="t('settings.v4.llmProviders.defaults.placeholder', 'Standardmodell wählen …')"
            @update:model-value="setDefault"
          />
          <span v-if="defaultRoute" class="llm-default-current">
            {{ defaultRoute.provider_id }} · {{ defaultRoute.model }}
          </span>
        </div>
      </Card>

      <Card
        v-for="provider in providersStore.providers"
        :key="provider.id"
        :title="provider.label"
        :subtitle="provider.base_url || ''"
      >
        <template #right>
          <Badge :variant="statusBadgeVariant(provider)">
            {{ statusLabel(provider) }}
          </Badge>
        </template>

        <div class="llm-card-body">
          <div v-if="providersStore.entries[provider.id]" class="llm-key-line">
            <span class="llm-key-line__label">
              {{ t('settings.v4.llmProviders.keyLabel', 'API-Key (maskiert)') }}
            </span>
            <code class="llm-key-line__value">
              {{ providersStore.entries[provider.id].masked_value }}
            </code>
          </div>

          <div class="llm-key-form">
            <Input
              v-model="ensureDraft(provider.id).apiKey"
              type="password"
              autocomplete="off"
              spellcheck="false"
              :placeholder="t('settings.v4.llmProviders.keyPlaceholder', 'Neuen API-Key einfügen …')"
            />
            <Input
              v-if="provider.type === 'openai_compatible'"
              v-model="ensureDraft(provider.id).baseUrl"
              :placeholder="t('settings.v4.llmProviders.baseUrlPlaceholder', 'https://api.example.com/v1')"
            />
          </div>

          <div class="llm-actions">
            <button
              type="button"
              class="llm-btn llm-btn--primary"
              :disabled="!ensureDraft(provider.id).apiKey.trim() || providersStore.busy[provider.id]"
              @click="save(provider)"
            >
              {{ t('settings.v4.llmProviders.actions.save', 'Speichern') }}
            </button>
            <button
              type="button"
              class="llm-btn"
              :disabled="providersStore.busy[provider.id]"
              @click="runTest(provider)"
            >
              {{ t('settings.v4.llmProviders.actions.test', 'Test') }}
            </button>
            <button
              type="button"
              class="llm-btn"
              :disabled="providersStore.busy[provider.id]"
              @click="loadModels(provider)"
            >
              {{ t('settings.v4.llmProviders.actions.refreshModels', 'Modelle laden') }}
            </button>
            <button
              v-if="providersStore.hasKey(provider.id)"
              type="button"
              class="llm-btn llm-btn--danger"
              :disabled="providersStore.busy[provider.id]"
              @click="disconnect(provider)"
            >
              {{ t('settings.v4.llmProviders.actions.disconnect', 'Trennen') }}
            </button>
          </div>

          <div
            v-if="ensureDraft(provider.id).testMessage"
            class="llm-test-result"
            :class="{ 'llm-test-result--ok': ensureDraft(provider.id).testOk, 'llm-test-result--fail': ensureDraft(provider.id).testOk === false }"
          >
            {{ ensureDraft(provider.id).testMessage }}
          </div>

          <div v-if="(providersStore.models[provider.id]?.models?.length ?? 0) > 0" class="llm-model-list">
            <span class="llm-model-list__title">
              {{ t('settings.v4.llmProviders.models.title', 'Modelle') }}
              <small>({{ providersStore.models[provider.id].models[0].source }})</small>
            </span>
            <ul>
              <li v-for="model in providersStore.models[provider.id].models" :key="model.id">
                {{ model.id }}
              </li>
            </ul>
          </div>
        </div>
      </Card>
    </div>
  </AppShell>
</template>

<style scoped>
.llm-providers-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 16px;
  padding: 16px;
}
.llm-card-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.llm-key-line {
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: var(--surface-muted, rgba(0, 0, 0, 0.03));
  padding: 8px 10px;
  border-radius: var(--r-4, 8px);
}
.llm-key-line__label {
  font-size: 12px;
  color: var(--text-secondary);
}
.llm-key-line__value {
  font-family: var(--font-mono, monospace);
  font-size: 13px;
  color: var(--text-primary);
}
.llm-key-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.llm-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.llm-btn {
  border: 1px solid var(--hairline);
  background: var(--surface-elevated, #fff);
  padding: 6px 12px;
  border-radius: var(--r-4, 8px);
  font-size: 13px;
  cursor: pointer;
}
.llm-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.llm-btn--primary {
  background: var(--accent, #0a84ff);
  color: #fff;
  border-color: var(--accent, #0a84ff);
}
.llm-btn--danger {
  color: var(--danger, #d33);
  border-color: var(--danger, #d33);
}
.llm-test-result {
  font-size: 13px;
  padding: 6px 10px;
  border-radius: var(--r-4, 8px);
  background: var(--surface-muted, rgba(0, 0, 0, 0.04));
}
.llm-test-result--ok { color: var(--success, #176f3a); }
.llm-test-result--fail { color: var(--danger, #d33); }
.llm-model-list ul {
  margin: 4px 0 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--text-secondary);
  max-height: 140px;
  overflow-y: auto;
}
.llm-model-list__title {
  font-size: 12px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.llm-default-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.llm-default-current {
  font-family: var(--font-mono, monospace);
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
