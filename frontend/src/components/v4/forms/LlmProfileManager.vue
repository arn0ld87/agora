<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Card from './Card.vue'
import { useLlmProfilesStore } from '@/store/llmProfiles'
import type { LlmProfile, LlmProvider } from '@/contracts/llmProfileContract'

const { t } = useI18n()
const store = useLlmProfilesStore()

// ---------------------------------------------------------------------------
// Preset-Definitionen (analog zu LlmProviderCard)
// ---------------------------------------------------------------------------
interface Preset {
  key: LlmProvider
  label: string
  url: string
  needsKey: boolean
}

const PRESETS = computed<Preset[]>(() => [
  { key: 'ollama',     label: t('settings.v4.llmProfiles.presets.ollama'),     url: 'http://localhost:11434/v1',                               needsKey: false },
  { key: 'openai',    label: t('settings.v4.llmProfiles.presets.openai'),    url: 'https://api.openai.com/v1',                               needsKey: true  },
  { key: 'gemini',    label: t('settings.v4.llmProfiles.presets.gemini'),    url: 'https://generativelanguage.googleapis.com/v1beta/openai', needsKey: true  },
  { key: 'anthropic', label: t('settings.v4.llmProfiles.presets.anthropic'), url: 'https://api.anthropic.com/v1',                            needsKey: true  },
  { key: 'custom',    label: t('settings.v4.llmProfiles.presets.custom'),    url: '',                                                        needsKey: false },
])

// ---------------------------------------------------------------------------
// Form-State
// ---------------------------------------------------------------------------
type FormMode = 'idle' | 'create' | 'edit'
const formMode = ref<FormMode>('idle')
const editingId = ref<string | null>(null)
// is_default vom existierenden Profil beim Edit übernehmen, sonst löscht
// das Hardcoden `is_default: false` den Standard-Status beim Bearbeiten.
const editingIsDefault = ref(false)

const formName     = ref('')
const formProvider = ref<LlmProvider>('ollama')
const formBaseUrl  = ref('')
const formModel    = ref('')

// api_key-Edit-Semantik:
// 'unchanged' → api_key: null senden (Server lässt Key unberührt)
// 'clear'     → api_key: ""  senden (Server entfernt Key)
// 'new'       → api_key: formApiKeyDraft.value senden
type ApiKeyEditMode = 'unchanged' | 'clear' | 'new'
const apiKeyEditMode = ref<ApiKeyEditMode>('unchanged')
const apiKeyDraft    = ref('')

// ---------------------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------------------
function resetForm(): void {
  formName.value     = ''
  formProvider.value = 'ollama'
  formBaseUrl.value  = ''
  formModel.value    = ''
  apiKeyEditMode.value = 'unchanged'
  apiKeyDraft.value    = ''
}

function openCreate(): void {
  resetForm()
  editingId.value = null
  formMode.value  = 'create'
}

function openEdit(profile: LlmProfile): void {
  formName.value     = profile.name
  formProvider.value = profile.provider
  formBaseUrl.value  = profile.base_url
  formModel.value    = profile.model_name
  // api_key bleibt initial leer ("unchanged")
  apiKeyEditMode.value = 'unchanged'
  apiKeyDraft.value    = ''
  editingId.value        = profile.id
  editingIsDefault.value = profile.is_default
  formMode.value         = 'edit'
}

function cancel(): void {
  formMode.value         = 'idle'
  editingId.value        = null
  editingIsDefault.value = false
  resetForm()
}

function selectPreset(preset: Preset): void {
  formProvider.value = preset.key
  formBaseUrl.value  = preset.url
  if (!preset.needsKey) {
    apiKeyEditMode.value = 'unchanged'
    apiKeyDraft.value    = ''
  }
}

function onApiKeyInput(e: Event): void {
  const val = (e.target as HTMLInputElement).value
  apiKeyDraft.value    = val
  apiKeyEditMode.value = 'new'
}

function clearKey(): void {
  apiKeyEditMode.value = 'clear'
  apiKeyDraft.value    = ''
}

function undoClearKey(): void {
  apiKeyEditMode.value = 'unchanged'
  apiKeyDraft.value    = ''
}

// ---------------------------------------------------------------------------
// Computed: welcher api_key-Wert wird gesendet?
// ---------------------------------------------------------------------------
const resolvedApiKey = computed<string | null>(() => {
  if (formMode.value === 'create') {
    // Neues Profil: leeres Feld → null (kein Key)
    return apiKeyDraft.value === '' ? null : apiKeyDraft.value
  }
  // Edit-Pfade
  if (apiKeyEditMode.value === 'unchanged') return null
  if (apiKeyEditMode.value === 'clear')     return ''
  return apiKeyDraft.value
})

// ---------------------------------------------------------------------------
// Submit
// ---------------------------------------------------------------------------
async function submit(): Promise<void> {
  const req = {
    name:       formName.value.trim(),
    provider:   formProvider.value,
    base_url:   formBaseUrl.value.trim(),
    model_name: formModel.value.trim(),
    api_key:    resolvedApiKey.value,
    // Edit: bestehenden is_default beibehalten — sonst verliert das aktuelle
    // Default-Profil beim Bearbeiten seinen Status. Create: immer false; der
    // User setzt den Default explizit über den „Als Standard"-Button.
    is_default: formMode.value === 'edit' ? editingIsDefault.value : false,
  }

  if (formMode.value === 'create') {
    await store.create(req)
  } else if (formMode.value === 'edit' && editingId.value) {
    await store.update(editingId.value, req)
  }

  if (!store.error) {
    cancel()
  }
}

async function handleDelete(profile: LlmProfile): Promise<void> {
  if (!window.confirm(t('settings.v4.llmProfiles.deleteConfirm'))) return
  await store.remove(profile.id)
}

async function handleSetDefault(profile: LlmProfile): Promise<void> {
  await store.setDefault(profile.id)
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
onMounted(() => {
  void store.fetch()
})
</script>

<template>
  <Card
    :title="t('settings.v4.llmProfiles.title')"
    :subtitle="t('settings.v4.llmProfiles.subtitle')"
  >
    <!-- Fehleranzeige -->
    <div v-if="store.error" class="pm-error" role="alert">
      {{ store.error }}
    </div>

    <!-- Ladezustand -->
    <div v-if="store.loading" class="pm-loading">…</div>

    <!-- Profil-Liste -->
    <template v-if="!store.loading">
      <div v-if="store.profiles.length === 0 && formMode === 'idle'" class="pm-empty">
        {{ t('settings.v4.llmProfiles.emptyState') }}
      </div>

      <ul v-else class="pm-list">
        <li
          v-for="profile in store.profiles"
          :key="profile.id"
          class="pm-item"
          :class="{ 'pm-item--editing': editingId === profile.id && formMode === 'edit' }"
        >
          <div class="pm-item-header">
            <span class="pm-item-name">{{ profile.name }}</span>
            <span class="pm-provider-badge">{{ profile.provider }}</span>
            <span class="pm-item-model">{{ profile.model_name }}</span>
            <span v-if="profile.is_default" class="pm-default-badge">
              {{ t('settings.v4.llmProfiles.defaultBadge') }}
            </span>
          </div>
          <div class="pm-item-actions">
            <button
              type="button"
              class="pm-action-btn"
              :disabled="store.saving"
              @click="openEdit(profile)"
            >
              {{ t('settings.v4.llmProfiles.editBtn') }}
            </button>
            <button
              type="button"
              class="pm-action-btn"
              :disabled="profile.is_default || store.saving"
              @click="handleSetDefault(profile)"
            >
              {{ t('settings.v4.llmProfiles.setDefaultBtn') }}
            </button>
            <button
              type="button"
              class="pm-action-btn pm-action-btn--danger"
              :disabled="store.saving"
              @click="handleDelete(profile)"
            >
              {{ t('settings.v4.llmProfiles.deleteBtn') }}
            </button>
          </div>
        </li>
      </ul>
    </template>

    <!-- Inline-Formular (Create oder Edit) -->
    <div v-if="formMode !== 'idle'" class="pm-form">
      <!-- Preset-Auswahl -->
      <div class="llm-presets">
        <button
          v-for="p in PRESETS"
          :key="p.key"
          type="button"
          class="llm-preset"
          :class="{ 'llm-preset--active': formProvider === p.key }"
          @click="selectPreset(p)"
        >
          {{ p.label }}
        </button>
      </div>

      <div class="llm-fields">
        <!-- Name -->
        <div class="llm-field">
          <label class="llm-label" for="pm-name">{{ t('settings.v4.llmProfiles.nameLabel') }}</label>
          <input
            id="pm-name"
            v-model="formName"
            type="text"
            class="llm-input"
            :placeholder="t('settings.v4.llmProfiles.nameLabel')"
          />
        </div>

        <!-- Base URL -->
        <div class="llm-field">
          <label class="llm-label" for="pm-base-url">{{ t('settings.v4.llmProfiles.baseUrlLabel') }}</label>
          <input
            id="pm-base-url"
            v-model="formBaseUrl"
            type="text"
            class="llm-input"
            placeholder="https://..."
          />
        </div>

        <!-- Modell -->
        <div class="llm-field">
          <label class="llm-label" for="pm-model">{{ t('settings.v4.llmProfiles.modelLabel') }}</label>
          <input
            id="pm-model"
            v-model="formModel"
            type="text"
            class="llm-input"
            placeholder="qwen2.5:32b"
          />
        </div>

        <!-- API Key -->
        <div class="llm-field">
          <label class="llm-label" for="pm-api-key">{{ t('settings.v4.llmProfiles.apiKeyLabel') }}</label>
          <div class="pm-apikey-row">
            <input
              id="pm-api-key"
              :value="apiKeyDraft"
              type="password"
              class="llm-input llm-input--mono pm-apikey-input"
              :placeholder="formMode === 'edit' ? t('settings.v4.llmProfiles.apiKeyPlaceholderEdit') : 'sk-…'"
              :disabled="apiKeyEditMode === 'clear'"
              autocomplete="off"
              @input="onApiKeyInput"
            />
            <!-- Edit-Mode: Key-Aktionen -->
            <template v-if="formMode === 'edit'">
              <button
                v-if="apiKeyEditMode !== 'clear'"
                type="button"
                class="pm-action-btn pm-action-btn--danger"
                @click="clearKey"
              >
                {{ t('settings.v4.llmProfiles.clearKeyBtn') }}
              </button>
              <button
                v-else
                type="button"
                class="pm-action-btn"
                @click="undoClearKey"
              >
                {{ t('settings.v4.llmProfiles.cancelBtn') }}
              </button>
            </template>
          </div>
          <span v-if="apiKeyEditMode === 'clear'" class="pm-key-hint">
            {{ t('settings.v4.llmProfiles.clearKeyBtn') }} — {{ t('settings.v4.llmProfiles.apiKeyPlaceholderEdit') }}
          </span>
        </div>
      </div>

      <!-- Form-Footer -->
      <div class="llm-footer">
        <button
          type="button"
          class="pm-action-btn"
          :disabled="store.saving"
          @click="cancel"
        >
          {{ t('settings.v4.llmProfiles.cancelBtn') }}
        </button>
        <button
          type="button"
          class="v4-btn v4-btn--primary"
          :disabled="store.saving || !formName.trim() || !formBaseUrl.trim() || !formModel.trim()"
          @click="submit"
        >
          {{ t('settings.v4.llmProfiles.saveBtn') }}
        </button>
      </div>
    </div>

    <!-- "Neues Profil"-Button (nur wenn kein Formular offen) -->
    <div v-if="formMode === 'idle'" class="pm-add-row">
      <button
        type="button"
        class="v4-btn v4-btn--primary"
        :disabled="store.loading"
        @click="openCreate"
      >
        {{ t('settings.v4.llmProfiles.addBtn') }}
      </button>
    </div>
  </Card>
</template>

<style scoped>
/* Liste */
.pm-list {
  list-style: none;
  margin: 0 0 16px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pm-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid var(--hairline);
  border-radius: var(--r-4, 8px);
  background: var(--surface-elevated, #fff);
}

.pm-item--editing {
  border-color: var(--accent);
}

.pm-item-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.pm-item-name {
  font-family: var(--font-sans);
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.pm-provider-badge {
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: var(--r-5, 10px);
  border: 1px solid var(--hairline);
  color: var(--text-secondary);
  background: var(--surface-elevated, #fff);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.pm-item-model {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-secondary);
}

.pm-default-badge {
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--r-5, 10px);
  background: var(--accent-subtle, #f0f5ff);
  color: var(--accent);
  border: 1px solid var(--accent);
}

.pm-item-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

/* Buttons */
.pm-action-btn {
  font-family: var(--font-sans);
  font-size: 12px;
  font-weight: 500;
  padding: 4px 10px;
  border: 1px solid var(--hairline);
  border-radius: var(--r-4, 8px);
  background: var(--surface-elevated, #fff);
  color: var(--text-secondary);
  cursor: pointer;
  transition: border-color 80ms ease, color 80ms ease;
}
.pm-action-btn:hover:not(:disabled) {
  border-color: var(--hairline-strong);
  color: var(--text-primary);
}
.pm-action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.pm-action-btn--danger:hover:not(:disabled) {
  border-color: var(--status-red, #c0392b);
  color: var(--status-red, #c0392b);
}

/* Inline-Form */
.pm-form {
  border: 1px solid var(--hairline);
  border-radius: var(--r-4, 8px);
  padding: 16px;
  background: var(--surface-elevated, #fff);
  margin-bottom: 16px;
}

.pm-add-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

/* API-Key-Zeile */
.pm-apikey-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.pm-apikey-input {
  flex: 1;
}

.pm-key-hint {
  font-size: 12px;
  color: var(--text-secondary);
}

/* Zustände */
.pm-empty {
  font-family: var(--font-sans);
  font-size: 14px;
  color: var(--text-secondary);
  padding: 8px 0 16px;
}

.pm-loading {
  font-family: var(--font-sans);
  font-size: 14px;
  color: var(--text-secondary);
  padding: 8px 0;
}

.pm-error {
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--status-red, #c0392b);
  padding: 8px 12px;
  border: 1px solid var(--status-red, #c0392b);
  border-radius: var(--r-4, 8px);
  margin-bottom: 12px;
}

/* Wiederverwendete LlmProviderCard-Klassen */
.llm-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 20px;
}

.llm-preset {
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  padding: 6px 14px;
  border: 1px solid var(--hairline);
  border-radius: var(--r-5, 10px);
  background: var(--surface-elevated, #fff);
  color: var(--text-secondary);
  cursor: pointer;
  transition: border-color 80ms ease, color 80ms ease;
}
.llm-preset:hover {
  border-color: var(--hairline-strong);
  color: var(--text-primary);
}
.llm-preset--active {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-subtle, #f0f5ff);
}

.llm-fields { display: flex; flex-direction: column; gap: 16px; }
.llm-field  { display: flex; flex-direction: column; gap: 6px; }

.llm-label {
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.llm-input {
  font-family: var(--font-sans);
  font-size: 14px;
  padding: 9px 12px;
  border: 1px solid var(--hairline);
  border-radius: var(--r-4, 8px);
  background: var(--surface-elevated, #fff);
  color: var(--text-primary);
}
.llm-input--mono { font-family: var(--font-mono); }
.llm-input:hover { border-color: var(--hairline-strong); }
.llm-input:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--focus-ring);
}
.llm-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.llm-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
}
</style>
