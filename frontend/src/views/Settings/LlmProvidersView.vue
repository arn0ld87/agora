<script setup lang="ts">
/**
 * LlmProvidersView — Workspace-weite LLM-Provider-Konfiguration.
 *
 * Pro Katalog-Provider (statische Registry-Metadaten aus GET /api/llm/providers)
 * eine Karte mit dem kanonischen Connection-Lifecycle
 * (GET/PUT/DELETE/test/models unter /api/llm/provider-connections, Onboarding
 * Slice 3 Task 5):
 *   - Status-Badge: nicht konfiguriert / konfiguriert / verbunden / eingeschränkt
 *     / Fehler / getrennt — oder ehrlich "nicht unterstützt" für
 *     Subscription-/CLI-Bridges (409 provider_unsupported), NIE als verbunden
 *     vorgetäuscht.
 *   - Key-Eingabe (type=password, nur für api_key-Provider) + Base-URL
 *     (Pflicht für openai_compatible, Loopback-Ausnahme für lokales Ollama).
 *   - Buttons: Verbindung speichern, testen, Modelle laden, trennen.
 *   - Sichtbare Discovery-Modellliste (Source: live/cached/fallback/custom).
 *   - Inline Global-Default-Picker (Workspace-Default-Routing, unverändert).
 *
 * Klartext-Keys verlassen dieses View nur als PUT-Body-Feld Richtung Backend
 * und werden nie im Pinia-State oder localStorage gehalten (siehe
 * store/aiModels.ts).
 */
import { computed, onMounted, reactive, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import Card from '@/components/v4/forms/Card.vue'
import Badge from '@/components/v4/forms/Badge.vue'
import Input from '@/components/v4/forms/Input.vue'
import AiModelPicker from '@/components/v4/forms/AiModelPicker.vue'
import { useLlmProvidersStore, useLlmRoutingDefaultsStore } from '@/store/aiModels'
import { useAiModelRefAdapter } from '@/composables/useAiModelRefAdapter'
import type { ProviderDescriptor } from '@/contracts/llmRoutingContract'
import type { LlmRoute } from '@/contracts/llmRoute'
import type { ProviderProbeStatus } from '@/contracts/aiProviderContract'
import type { AiModelRef } from '@/contracts/aiModelRef'

const { t } = useI18n()

const providersStore = useLlmProvidersStore()
const defaultsStore = useLlmRoutingDefaultsStore()
const adapter = useAiModelRefAdapter()

const BREADCRUMBS = [
  { label: 'Settings', to: { name: 'SettingsGeneral' } },
  { label: t('settings.v4.llmProviders.title', 'LLM-Provider') },
]

interface DraftState {
  apiKey: string
  baseUrl: string
}

const drafts = reactive<Record<string, DraftState>>({})

function ensureDraft(p: ProviderDescriptor): DraftState {
  if (!(p.id in drafts)) {
    const connection = providersStore.connections[p.id]
    drafts[p.id] = {
      apiKey: '',
      baseUrl: connection?.base_url || p.base_url || '',
    }
  }
  return drafts[p.id]
}

/**
 * 409 provider_unsupported (Subscription-/CLI-Bridges wie opencode_go,
 * github_copilot): server-seitig UND client-seitig aus der Registry-Metadatik
 * erkennbar, bevor überhaupt ein PUT/Test versucht wird — nie eine
 * Verbindung vortäuschen.
 */
function isUnsupported(p: ProviderDescriptor): boolean {
  return p.supports_models_endpoint === false || providersStore.connectionUnsupported[p.id] === true
}

function isConfigured(p: ProviderDescriptor): boolean {
  return providersStore.isConnectionConfigured(p.id)
}

function isOllama(p: ProviderDescriptor): boolean {
  return p.type === 'ollama'
}

function statusTone(p: ProviderDescriptor): 'gray' | 'green' | 'orange' | 'red' {
  if (isUnsupported(p)) return 'gray'
  const connection = providersStore.connections[p.id]
  if (!connection) return 'gray'
  switch (connection.status) {
    case 'connected':
      return 'green'
    case 'degraded':
      return 'orange'
    case 'error':
    case 'disconnected':
      return 'red'
    default:
      return 'gray'
  }
}

function statusLabel(p: ProviderDescriptor): string {
  if (isUnsupported(p)) return t('settings.v4.llmProviders.status.unsupported', 'Nicht unterstützt')
  const connection = providersStore.connections[p.id]
  if (!connection) return t('settings.v4.llmProviders.status.notConfigured', 'Nicht konfiguriert')
  switch (connection.status) {
    case 'connected':
      return t('settings.v4.llmProviders.status.connected', 'Verbunden')
    case 'degraded':
      return t('settings.v4.llmProviders.status.degraded', 'Eingeschränkt')
    case 'error':
      return t('settings.v4.llmProviders.status.error', 'Fehler')
    case 'disconnected':
      return t('settings.v4.llmProviders.status.disconnected', 'Getrennt')
    default:
      return t('settings.v4.llmProviders.status.configured', 'Konfiguriert (ungetestet)')
  }
}

function testStatusLabel(status: ProviderProbeStatus, modelsFound: number): string {
  if (status === 'available') {
    return t('settings.v4.llmProviders.test.available', { count: modelsFound })
  }
  return t(`settings.v4.llmProviders.test.${status}`)
}

async function save(p: ProviderDescriptor): Promise<void> {
  if (isUnsupported(p)) return
  const draft = ensureDraft(p)
  const baseUrl = draft.baseUrl.trim()
  const apiKey = draft.apiKey.trim()
  try {
    await providersStore.upsertConnection(p.id, {
      display_name: p.label,
      provider_kind: p.type,
      base_url: baseUrl || null,
      enabled: true,
      ...(apiKey ? { api_key: apiKey } : {}),
    })
    draft.apiKey = ''
  } catch {
    // Fehlertext liegt strukturiert in providersStore.connectionError[p.id]
    // und wird im Template angezeigt — kein stiller Fallback.
  }
}

async function runTest(p: ProviderDescriptor): Promise<void> {
  if (isUnsupported(p) || !isConfigured(p)) return
  try {
    await providersStore.testConnection(p.id)
  } catch {
    // s.o. — Fehler liegt in providersStore.connectionError[p.id].
  }
}

async function loadModels(p: ProviderDescriptor): Promise<void> {
  if (isUnsupported(p) || !isConfigured(p)) return
  try {
    await providersStore.fetchConnectionModels(p.id)
  } catch {
    // s.o.
  }
}

async function disconnect(p: ProviderDescriptor): Promise<void> {
  await providersStore.removeConnection(p.id)
  delete drafts[p.id]
}

const defaultRoute = computed<LlmRoute | null>(() => {
  const r = defaultsStore.globalDefault
  if (!r?.provider_id || !r?.model) return null
  return r
})

// Slice 5.4: AiModelRef-Aequivalent der aktuellen Default-Route.
// Statt LlmRoute → AiModelRef-Konvertierung in der View, nutzen wir
// den Adapter bidirektional: setDefault empfängt AiModelRef, konvertiert
// nach LlmRoute für den v3-Store. Picker zeigt die AiModelRef-Form.
const defaultAiRef = computed<AiModelRef | null>(() => {
  if (!defaultRoute.value) return null
  return adapter.toAiModelRef(defaultRoute.value)
})

async function setDefault(aiRef: AiModelRef | null): Promise<void> {
  if (!aiRef) return
  const llmRoute = adapter.toLlmRoute(aiRef)
  await defaultsStore.setGlobalDefault(llmRoute)
}

onMounted(async () => {
  await Promise.all([providersStore.loadProviders(), providersStore.loadConnections()])
  await defaultsStore.load()
})

// Klartext-Key-Drafts nie über die Lebensdauer des Views hinaus im Speicher
// belassen — beim Unmount werden alle Eingabefelder verworfen.
onBeforeUnmount(() => {
  for (const key of Object.keys(drafts)) {
    delete drafts[key]
  }
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
          <AiModelPicker
            :model-value="defaultAiRef"
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
        data-testid="provider-card"
        :data-provider-id="provider.id"
      >
        <template #right>
          <Badge :tone="statusTone(provider)" data-testid="provider-status-badge">
            {{ statusLabel(provider) }}
          </Badge>
        </template>

        <div class="llm-card-body">
          <p v-if="isUnsupported(provider)" class="llm-unsupported-notice" data-testid="provider-unsupported-notice">
            {{ t('settings.v4.llmProviders.unsupportedNotice', 'Dieser Anbieter ist eine Subscription-/CLI-Bridge und wird für Provider-Verbindungen nicht unterstützt.') }}
          </p>

          <template v-else>
            <div class="llm-key-form">
              <Input
                v-if="!isOllama(provider)"
                v-model="ensureDraft(provider).apiKey"
                type="password"
                autocomplete="off"
                spellcheck="false"
                :placeholder="t('settings.v4.llmProviders.keyPlaceholder', 'Neuen API-Key einfügen …')"
              />
              <Input
                v-model="ensureDraft(provider).baseUrl"
                :placeholder="isOllama(provider)
                  ? t('settings.v4.llmProviders.localBaseUrlPlaceholder', 'http://localhost:11434')
                  : t('settings.v4.llmProviders.baseUrlPlaceholder', 'https://api.example.com/v1')"
              />
            </div>

            <div class="llm-actions">
              <button
                type="button"
                class="llm-btn llm-btn--primary"
                :disabled="providersStore.connectionBusy[provider.id]"
                @click="save(provider)"
              >
                {{ t('settings.v4.llmProviders.actions.save', 'Verbindung speichern') }}
              </button>
              <button
                type="button"
                class="llm-btn"
                :disabled="!isConfigured(provider) || providersStore.connectionBusy[provider.id]"
                @click="runTest(provider)"
              >
                {{ t('settings.v4.llmProviders.actions.test', 'Verbindung testen') }}
              </button>
              <button
                type="button"
                class="llm-btn"
                :disabled="!isConfigured(provider) || providersStore.connectionBusy[provider.id]"
                @click="loadModels(provider)"
              >
                {{ t('settings.v4.llmProviders.actions.refreshModels', 'Modelle laden') }}
              </button>
              <button
                v-if="isConfigured(provider)"
                type="button"
                class="llm-btn llm-btn--danger"
                :disabled="providersStore.connectionBusy[provider.id]"
                @click="disconnect(provider)"
              >
                {{ t('settings.v4.llmProviders.actions.disconnect', 'Verbindung trennen') }}
              </button>
            </div>

            <div
              v-if="providersStore.connectionError[provider.id]"
              class="llm-test-result llm-test-result--fail"
              data-testid="provider-error"
            >
              {{ providersStore.connectionError[provider.id] }}
            </div>

            <div
              v-else-if="providersStore.connectionTestResults[provider.id]"
              class="llm-test-result"
              :class="{ 'llm-test-result--ok': providersStore.connectionTestResults[provider.id].status === 'available' }"
              data-testid="provider-test-result"
            >
              {{ testStatusLabel(
                providersStore.connectionTestResults[provider.id].status,
                providersStore.connectionTestResults[provider.id].models_found,
              ) }}
            </div>

            <div v-if="(providersStore.connectionModels[provider.id]?.length ?? 0) > 0" class="llm-model-list">
              <span class="llm-model-list__title">
                {{ t('settings.v4.llmProviders.models.title', 'Entdeckte Modelle') }}
                <small>({{ providersStore.connectionModels[provider.id][0].source }})</small>
              </span>
              <ul>
                <li v-for="model in providersStore.connectionModels[provider.id]" :key="model.model_id">
                  {{ model.model_id }}
                </li>
              </ul>
            </div>
          </template>
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
