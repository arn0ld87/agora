<script setup lang="ts">
/**
 * EnvSetupModelPanel — Modell-/Sprach-/Runtime-Provider-Auswahl (Step 2).
 *
 * Issue #834: v3-Profil-Legacy-Picker entfernt.
 * Issue #890: kanonischer AiModelPicker (`modelRef` / `update:modelRef`)
 * als Modell-Kanon-Senke eingebunden. Die bestehenden Props/Emits
 * `modelOption`/`customModel`/`modelOptions` und
 * `update:modelOption`/`update:customModel` bleiben bestehen — sie
 * bedienen weiterhin den Legacy-Runtime-Provider-Pfad (siehe
 * `Step2EnvSetup.vue`, `useRuntimeLlmOptions`). Beide Pfade sind
 * gegenseitig exklusiv; die Steuerung (welcher Pfad aktiv ist, disabled-
 * Zustand) liegt beim Parent, nicht hier.
 */
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Field from '../ui/Field.vue'
import Select from '../ui/Select.vue'
import AiModelPicker from '../v4/forms/AiModelPicker.vue'
import type { AiModelRef } from '@/contracts/aiModelRef'

const { t } = useI18n()

const props = defineProps({
  modelOption: { type: String, required: true },
  modelOptions: { type: Array, required: true },
  customModel: { type: String, default: '' },
  language: { type: String, required: true },
  loadingModels: { type: Boolean, default: false },
  runtimeProviderEnabled: { type: Boolean, default: false },
  serverDefaultRequiresOllama: { type: Boolean, default: false },
  ollamaReachable: { type: Boolean, default: false },
  defaultProvider: { type: String, default: '' },
  agentToolsEnabled: { type: Boolean, default: false },
  maxToolCallsPerAction: { type: Number, default: 0 },
  runtimeProvider: { type: String, default: 'default' },
  runtimeProviderOptions: { type: Array, required: true },
  runtimeApiKey: { type: String, default: '' },
  runtimeBaseUrl: { type: String, default: '' },
  runtimeApiKeyMissing: { type: Boolean, default: false },
  providerDbHasKey: { type: Boolean, default: false },
  providerDbKeyChecking: { type: Boolean, default: false },
  showSessionKeyOverride: { type: Boolean, default: false },
  isPreparing: { type: Boolean, default: false },
  modelRef: { type: Object as () => AiModelRef | null, default: null },
  modelPickerDisabled: { type: Boolean, default: false },
})

// Issue #890: sobald eine kanonische Modellauswahl aktiv ist, ist der
// Runtime-Provider-Block deaktiviert (gegenseitiger Ausschluss, siehe
// Step2EnvSetup.vue). Der Backend-400-Guard (ai_model_ref + llm_provider)
// kann so nie ausgeloest werden.
const runtimeProviderBlockDisabled = computed(() => props.modelRef !== null)

const emit = defineEmits<{
  'update:modelOption': [value: string]
  'update:customModel': [value: string]
  'update:language': [value: string]
  'update:runtimeProvider': [value: string]
  'update:runtimeApiKey': [value: string]
  'update:runtimeBaseUrl': [value: string]
  'update:showSessionKeyOverride': [value: boolean]
  'update:modelRef': [value: AiModelRef | null]
}>()

const showRuntimeOptions = ref(false)
</script>

<template>
  <div class="env-setup-model-panel">
    <p v-if="agentToolsEnabled" class="hint warning">
      {{ t('step2.agentTools.warning', { count: maxToolCallsPerAction }) }}
    </p>

    <div class="setup-grid">
      <!-- Kanonische Modell-Auswahl (AiModelRef) -->
      <div class="setup-cell setup-cell--wide">
        <label class="field-label">{{ t('step2.model.label') }}</label>
        <AiModelPicker
          :model-value="modelRef"
          mode="chat"
          :disabled="modelPickerDisabled"
          @update:model-value="emit('update:modelRef', $event)"
        />
      </div>

      <!-- Model (Legacy-Runtime-Provider-Pfad) -->
      <div class="setup-cell">
        <Select
          :model-value="modelOption"
          :label="t('step2.model.label')"
          :options="modelOptions"
          @update:model-value="emit('update:modelOption', $event)"
        />
        <p class="hint" v-if="loadingModels">{{ t('step2.model.loadingModels') }}</p>
        <p class="hint" v-else-if="!runtimeProviderEnabled && serverDefaultRequiresOllama && !ollamaReachable">{{ t('step2.model.noOllama') }}</p>
        <p class="hint" v-else-if="!runtimeProviderEnabled && defaultProvider === 'openai'">{{ t('step2.model.openAiDefault') }}</p>
      </div>

      <!-- Custom model input (when 'custom' chosen) -->
      <div class="setup-cell" v-if="modelOption === 'custom'">
        <Field
          :model-value="customModel"
          :label="t('step2.model.customLabel')"
          :placeholder="t('step2.model.customPlaceholder')"
          @update:model-value="emit('update:customModel', $event)"
        />
      </div>

      <div class="setup-cell setup-cell--wide">
        <button
          type="button"
          class="runtime-toggle"
          :aria-expanded="showRuntimeOptions"
          :disabled="runtimeProviderBlockDisabled"
          @click="showRuntimeOptions = !showRuntimeOptions"
        >
          <span>{{ t('step2.runtimeProvider.toggle') }}</span>
          <span class="meta">
            {{ runtimeProviderEnabled ? t('step2.runtimeProvider.active') : t('step2.runtimeProvider.default') }}
          </span>
        </button>
        <div v-if="showRuntimeOptions && !runtimeProviderBlockDisabled" class="runtime-panel">
          <Select
            :model-value="runtimeProvider"
            :label="t('step2.runtimeProvider.label')"
            :options="runtimeProviderOptions"
            @update:model-value="emit('update:runtimeProvider', $event)"
          />
          <template v-if="runtimeProviderEnabled">
            <p v-if="providerDbKeyChecking" class="hint">
              {{ t('step2.runtimeProvider.checkingKey') }}
            </p>
            <template v-else-if="providerDbHasKey">
              <p class="hint info provider-override-banner" role="status">
                {{ t('step2.runtimeProvider.dbKeyPresentBanner', { provider: runtimeProvider }) }}
              </p>
              <label class="session-key-toggle">
                <input
                  type="checkbox"
                  :checked="showSessionKeyOverride"
                  @change="emit('update:showSessionKeyOverride', ($event.target as HTMLInputElement).checked)"
                />
                {{ t('step2.runtimeProvider.sessionKeyOverrideToggle') }}
              </label>
            </template>
            <p
              v-else-if="runtimeApiKeyMissing"
              class="hint warning provider-override-banner"
              role="alert"
            >
              {{ t('step2.runtimeProvider.noDbKeyBanner', { provider: runtimeProvider }) }}
            </p>
            <Field
              v-if="!providerDbHasKey || showSessionKeyOverride"
              :model-value="runtimeApiKey"
              type="password"
              :label="t('step2.runtimeProvider.sessionKeyLabel')"
              :placeholder="t('step2.runtimeProvider.apiKeyPlaceholder')"
              @update:model-value="emit('update:runtimeApiKey', $event)"
            />
            <Field
              :model-value="runtimeBaseUrl"
              :label="t('step2.runtimeProvider.baseUrl')"
              :placeholder="t('step2.runtimeProvider.baseUrlPlaceholder')"
              @update:model-value="emit('update:runtimeBaseUrl', $event)"
            />
          </template>
        </div>
      </div>

      <!-- Agent language -->
      <div class="setup-cell">
        <Select
          :model-value="language"
          :label="t('step2.language.label')"
          :options="[
            { value: 'de', label: t('step2.language.de') },
            { value: 'en', label: t('step2.language.en') },
          ]"
          @update:model-value="emit('update:language', $event)"
        />
        <p class="hint">{{ t('step2.language.hint') }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.setup-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--s-5) var(--s-7);
}
.setup-cell { display: flex; flex-direction: column; gap: var(--s-2); }
.setup-cell--wide { grid-column: 1 / -1; }
.field-label {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}

.runtime-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  width: 100%;
  min-height: var(--ctl-h-md);
  padding: 0 var(--ctl-pad-x);
  border: 1px solid var(--rule-strong);
  border-radius: var(--r-1);
  background: var(--bg-elevated);
  color: var(--fg);
  cursor: pointer;
  font-family: var(--ff-mono);
  font-size: 12px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
}
.runtime-toggle:hover { border-color: color-mix(in oklch, var(--fg) 30%, transparent); }
.runtime-panel {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--s-4);
  padding: var(--s-4);
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  background: var(--bg-subtle);
}

.hint {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  margin: 0;
}

@media (max-width: 720px) {
  .setup-grid { grid-template-columns: 1fr; }
  .runtime-panel { grid-template-columns: 1fr; }
}

.setup-cell,
.runtime-panel {
  background: var(--surface-inset, var(--bg-elevated));
  border-radius: var(--r-6, var(--r-1));
}
.runtime-panel {
  border: 1px solid var(--hairline, var(--rule));
  padding: var(--sp-4, var(--s-4));
}
.hint {
  color: var(--text-secondary, var(--fg-muted));
  font-family: var(--font-sans, var(--ff-sans));
  letter-spacing: 0;
  text-transform: none;
}
</style>
