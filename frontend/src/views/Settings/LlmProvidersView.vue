<script setup lang="ts">
/**
 * LlmProvidersView — Workspace-weite LLM-Provider-Konfiguration.
 *
 * Redesign PR 9 (Audit-Punkt 9 „Card-Kit statt Struktur“, §7 Zeile 5
 * „Settings-Provider als Liste“): die fruehere Card-pro-Provider-Grid
 * (bis zu drei Karten mit je vier Buttons gleichzeitig sichtbar) wird
 * durch Liste + Detail-Formular ersetzt — genau EIN Provider ist zur
 * Zeit im Formularzustand, alle anderen stehen nur als Zeile da.
 *
 * Pro Katalog-Provider (statische Registry-Metadaten aus GET /api/llm/providers)
 * der kanonische Connection-Lifecycle (GET/PUT/DELETE/test/models unter
 * /api/llm/provider-connections, Onboarding Slice 3 Task 5):
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
import { computed, onMounted, reactive, ref, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import SettingsOverlay from '@/components/v4/forms/SettingsOverlay.vue'
import Card from '@/components/v4/forms/Card.vue'
import Badge from '@/components/v4/forms/Badge.vue'
import Input from '@/components/v4/forms/Input.vue'
import Button from '@/components/v4/forms/Button.vue'
import AiModelPicker from '@/components/v4/forms/AiModelPicker.vue'
import { useLlmProvidersStore, useLlmRoutingDefaultsStore } from '@/store/aiModels'
import { useAiModelRefAdapter } from '@/composables/useAiModelRefAdapter'
import { useEffectiveModelSelection } from '@/composables/useEffectiveModelSelection'
import { LlmProviderListTestId } from '@/contracts/testIds'
import type { ProviderDescriptor } from '@/contracts/llmRoutingContract'
import type { LlmRoute } from '@/contracts/llmRoute'
import type { ProviderProbeStatus } from '@/contracts/aiProviderContract'
import type { AiModelRef } from '@/contracts/aiModelRef'

const { t } = useI18n()

const providersStore = useLlmProvidersStore()
const defaultsStore = useLlmRoutingDefaultsStore()
const adapter = useAiModelRefAdapter()
const effectiveModel = useEffectiveModelSelection()

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

// Redesign PR 9: genau ein Provider steht im Formularzustand. Ohne
// Auswahl faellt die Liste auf den ersten Katalog-Eintrag zurueck, statt
// eine leere Detailflaeche zu zeigen.
const selectedProviderId = ref<string | null>(null)
const selectedProvider = computed<ProviderDescriptor | null>(
  () => providersStore.providers.find((p) => p.id === selectedProviderId.value) ?? providersStore.providers[0] ?? null,
)

function selectProvider(id: string): void {
  selectedProviderId.value = id
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
  // Kanon: routing/defaults.global + active-config im Gleichschritt
  // (Phase-1 Konsolidierung, PHASE-1-DIVERGENZ.md).
  await effectiveModel.setGlobalSelection(aiRef)
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
    <SettingsOverlay>
      <PageHeader
        :title="t('settings.v4.llmProviders.title', 'LLM-Provider')"
        :subtitle="t('settings.v4.llmProviders.subtitle', 'Hinterlege API-Schlüssel, ziehe Modelle und wähle pro Schritt das passende Modell aus.')"
      />

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

      <div class="llm-providers-layout">
        <ul
          class="llm-provider-list"
          role="listbox"
          :aria-label="t('settings.v4.llmProviders.list.ariaLabel', 'Provider')"
          :data-testid="LlmProviderListTestId.list"
        >
          <li v-for="provider in providersStore.providers" :key="provider.id">
            <button
              type="button"
              role="option"
              class="llm-provider-list__row"
              :class="{ 'is-selected': selectedProvider?.id === provider.id }"
              :aria-selected="selectedProvider?.id === provider.id"
              :data-testid="LlmProviderListTestId.row"
              :data-provider-id="provider.id"
              @click="selectProvider(provider.id)"
            >
              <span class="llm-provider-list__label">{{ provider.label }}</span>
              <span class="llm-provider-list__type">{{ provider.type }}</span>
              <Badge :tone="statusTone(provider)" data-testid="provider-status-badge">
                {{ statusLabel(provider) }}
              </Badge>
            </button>
          </li>
        </ul>

        <div
          v-if="selectedProvider"
          class="llm-provider-detail"
          :data-testid="LlmProviderListTestId.detail"
          :data-provider-id="selectedProvider.id"
        >
          <div class="llm-provider-detail__head">
            <h3 class="llm-provider-detail__title">{{ selectedProvider.label }}</h3>
            <p v-if="selectedProvider.base_url" class="llm-provider-detail__subtitle">{{ selectedProvider.base_url }}</p>
          </div>

          <p
            v-if="isUnsupported(selectedProvider)"
            class="llm-unsupported-notice"
            data-testid="provider-unsupported-notice"
          >
            {{ t('settings.v4.llmProviders.unsupportedNotice', 'Dieser Anbieter ist eine Subscription-/CLI-Bridge und wird für Provider-Verbindungen nicht unterstützt.') }}
          </p>

          <template v-else>
            <div class="llm-key-form">
              <Input
                v-if="!isOllama(selectedProvider)"
                v-model="ensureDraft(selectedProvider).apiKey"
                type="password"
                autocomplete="off"
                spellcheck="false"
                :placeholder="t('settings.v4.llmProviders.keyPlaceholder', 'Neuen API-Key einfügen …')"
              />
              <Input
                v-model="ensureDraft(selectedProvider).baseUrl"
                :placeholder="isOllama(selectedProvider)
                  ? t('settings.v4.llmProviders.localBaseUrlPlaceholder', 'http://localhost:11434')
                  : t('settings.v4.llmProviders.baseUrlPlaceholder', 'https://api.example.com/v1')"
              />
            </div>

            <div class="llm-actions">
              <Button
                variant="primary"
                :loading="providersStore.connectionBusy[selectedProvider.id]"
                :data-testid="LlmProviderListTestId.saveButton"
                @click="save(selectedProvider)"
              >
                {{ t('settings.v4.llmProviders.actions.save', 'Verbindung speichern') }}
              </Button>
              <Button
                variant="secondary"
                :disabled="!isConfigured(selectedProvider)"
                :loading="providersStore.connectionBusy[selectedProvider.id]"
                :data-testid="LlmProviderListTestId.testButton"
                @click="runTest(selectedProvider)"
              >
                {{ t('settings.v4.llmProviders.actions.test', 'Verbindung testen') }}
              </Button>
              <Button
                variant="secondary"
                :disabled="!isConfigured(selectedProvider)"
                :loading="providersStore.connectionBusy[selectedProvider.id]"
                :data-testid="LlmProviderListTestId.refreshModelsButton"
                @click="loadModels(selectedProvider)"
              >
                {{ t('settings.v4.llmProviders.actions.refreshModels', 'Modelle laden') }}
              </Button>
              <Button
                v-if="isConfigured(selectedProvider)"
                variant="danger"
                :loading="providersStore.connectionBusy[selectedProvider.id]"
                :data-testid="LlmProviderListTestId.disconnectButton"
                @click="disconnect(selectedProvider)"
              >
                {{ t('settings.v4.llmProviders.actions.disconnect', 'Verbindung trennen') }}
              </Button>
            </div>

            <div
              v-if="providersStore.connectionError[selectedProvider.id]"
              class="llm-test-result llm-test-result--fail"
              data-testid="provider-error"
            >
              {{ providersStore.connectionError[selectedProvider.id] }}
            </div>

            <div
              v-else-if="providersStore.connectionTestResults[selectedProvider.id]"
              class="llm-test-result"
              :class="{ 'llm-test-result--ok': providersStore.connectionTestResults[selectedProvider.id].status === 'available' }"
              data-testid="provider-test-result"
            >
              {{ testStatusLabel(
                providersStore.connectionTestResults[selectedProvider.id].status,
                providersStore.connectionTestResults[selectedProvider.id].models_found,
              ) }}
            </div>

            <div v-if="(providersStore.connectionModels[selectedProvider.id]?.length ?? 0) > 0" class="llm-model-list">
              <span class="llm-model-list__title">
                {{ t('settings.v4.llmProviders.models.title', 'Entdeckte Modelle') }}
                <small>({{ providersStore.connectionModels[selectedProvider.id][0].source }})</small>
              </span>
              <ul>
                <li v-for="model in providersStore.connectionModels[selectedProvider.id]" :key="model.model_id">
                  {{ model.model_id }}
                </li>
              </ul>
            </div>
          </template>
        </div>
      </div>
    </SettingsOverlay>
  </AppShell>
</template>

<style scoped>
.llm-providers-layout {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
  gap: var(--sp-6);
  align-items: start;
  margin-top: var(--sp-5);
}

.llm-provider-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border: 1px solid var(--hairline);
  border-radius: var(--r-5);
  overflow: hidden;
}

.llm-provider-list__row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  width: 100%;
  padding: var(--sp-3) var(--sp-4);
  border: 0;
  border-bottom: 1px solid var(--hairline);
  background: transparent;
  color: var(--text-primary);
  font-family: var(--font-sans);
  font-size: var(--fs-small);
  text-align: left;
  cursor: pointer;
}

.llm-provider-list li:last-child .llm-provider-list__row {
  border-bottom: 0;
}

.llm-provider-list__row:hover {
  background: var(--surface-hover);
}

.llm-provider-list__row.is-selected {
  background: var(--accent-tint-bg);
}

.llm-provider-list__row:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.llm-provider-list__label {
  flex: 1;
  min-width: 0;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.llm-provider-list__type {
  font-family: var(--font-mono);
  font-size: var(--fs-mono);
  color: var(--text-tertiary);
}

.llm-provider-detail {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
  padding: var(--sp-5);
  border: 1px solid var(--hairline);
  border-radius: var(--r-5);
  background: var(--surface-elevated);
}

.llm-provider-detail__title {
  margin: 0;
  font-family: var(--font-sans);
  font-size: var(--fs-heading);
  color: var(--text-primary);
}

.llm-provider-detail__subtitle {
  margin: 4px 0 0;
  font-family: var(--font-mono);
  font-size: var(--fs-mono);
  color: var(--text-tertiary);
}

.llm-unsupported-notice {
  margin: 0;
  font-size: var(--fs-small);
  color: var(--text-secondary);
}

.llm-key-form {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.llm-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
}

.llm-test-result {
  font-size: var(--fs-small);
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--r-3);
  background: var(--surface-hover);
}
.llm-test-result--ok { color: var(--status-green); }
.llm-test-result--fail { color: var(--status-red); }
.llm-model-list ul {
  margin: 4px 0 0;
  padding-left: 18px;
  font-size: var(--fs-small);
  color: var(--text-secondary);
  max-height: 140px;
  overflow-y: auto;
}
.llm-model-list__title {
  font-size: var(--fs-label);
  color: var(--text-secondary);
  letter-spacing: 0.02em;
}
.llm-default-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.llm-default-current {
  font-family: var(--font-mono);
  font-size: var(--fs-small);
  color: var(--text-secondary);
}

@media (max-width: 900px) {
  .llm-providers-layout {
    grid-template-columns: 1fr;
  }
}
</style>
