<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Card from './Card.vue'
import { useSettingsStore } from '@/store/settings'

const { t } = useI18n()
const store = useSettingsStore()

interface Preset {
  key: string
  label: string
  url: string
  needsKey: boolean
}

const PRESETS = computed<Preset[]>(() => [
  { key: 'ollama',     label: t('settings.v4.llmProvider.presets.ollama'),     url: 'http://localhost:11434/v1',                               needsKey: false },
  { key: 'openai',    label: t('settings.v4.llmProvider.presets.openai'),    url: 'https://api.openai.com/v1',                               needsKey: true  },
  { key: 'gemini',    label: t('settings.v4.llmProvider.presets.gemini'),    url: 'https://generativelanguage.googleapis.com/v1beta/openai', needsKey: true  },
  { key: 'anthropic', label: t('settings.v4.llmProvider.presets.anthropic'), url: 'https://api.anthropic.com/v1',                            needsKey: true  },
  { key: 'custom',    label: t('settings.v4.llmProvider.presets.custom'),    url: '',                                                        needsKey: false },
])

const currentUrl = computed(() => (store.draft['LLM_BASE_URL'] as string) ?? '')
const activePreset = computed(
  () => PRESETS.value.find(p => p.url !== '' && p.url === currentUrl.value) ?? PRESETS.value[4],
)

const baseUrl = computed({
  get: () => currentUrl.value,
  set: (v: string) => { store.draft['LLM_BASE_URL'] = v },
})
const apiKey = computed({
  get: () => (store.draft['LLM_API_KEY'] as string) ?? '',
  set: (v: string) => { store.draft['LLM_API_KEY'] = v },
})
const modelName = computed({
  get: () => (store.draft['LLM_MODEL_NAME'] as string) ?? '',
  set: (v: string) => { store.draft['LLM_MODEL_NAME'] = v },
})

const saving    = ref(false)
const savedHint = ref(false)
const saveError = ref<string | null>(null)

function selectPreset(preset: Preset): void {
  store.draft['LLM_BASE_URL'] = preset.url
  if (!preset.needsKey) store.draft['LLM_API_KEY'] = ''
}

async function save(): Promise<void> {
  saving.value    = true
  savedHint.value = false
  saveError.value = null
  try {
    await store.saveSettings({ confirmSecrets: true })
    savedHint.value = true
    setTimeout(() => { savedHint.value = false }, 2500)
  } catch (e) {
    saveError.value = e instanceof Error ? e.message : String(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Card :title="t('settings.v4.llmProvider.title')" :subtitle="t('settings.v4.llmProvider.subtitle')">
    <!-- Preset-Auswahl -->
    <div class="llm-presets">
      <button
        v-for="p in PRESETS"
        :key="p.key"
        type="button"
        class="llm-preset v4-state-interactive"
        :class="{ 'llm-preset--active': activePreset.key === p.key }"
        @click="selectPreset(p)"
      >
        {{ p.label }}
      </button>
    </div>

    <div class="llm-fields">
      <!-- Base URL -->
      <div class="llm-field">
        <label class="llm-label" for="llm-base-url">{{ t('settings.v4.llmProvider.baseUrlLabel') }}</label>
        <input
          id="llm-base-url"
          v-model="baseUrl"
          type="text"
          class="llm-input"
          :placeholder="activePreset.url || 'https://...'"
        />
      </div>

      <!-- API Key (nur wenn nötig) -->
      <div v-if="activePreset.needsKey || activePreset.key === 'custom'" class="llm-field">
        <label class="llm-label" for="llm-api-key">{{ t('settings.v4.llmProvider.apiKeyLabel') }}</label>
        <input
          id="llm-api-key"
          v-model="apiKey"
          type="password"
          class="llm-input llm-input--mono"
          placeholder="sk-…"
          autocomplete="off"
        />
      </div>

      <!-- Modell -->
      <div class="llm-field">
        <label class="llm-label" for="llm-model">{{ t('settings.v4.llmProvider.modelLabel') }}</label>
        <input
          id="llm-model"
          v-model="modelName"
          type="text"
          class="llm-input"
          placeholder="qwen2.5:32b"
        />
      </div>
    </div>

    <!-- Footer -->
    <div class="llm-footer">
      <span v-if="savedHint" class="llm-saved">{{ t('settings.v4.llmProvider.savedHint') }}</span>
      <span v-if="saveError" class="llm-error">{{ saveError }}</span>
      <button
        type="button"
        class="v4-btn v4-btn--primary"
        :disabled="saving"
        @click="save"
      >
        {{ t('settings.v4.llmProvider.saveBtn') }}
      </button>
    </div>
  </Card>
</template>

<style scoped>
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
  border-radius: var(--r-5, 10px);
  /* v4-state-interactive liefert border/background/transition/hover/focus-ring/cursor */
  color: var(--text-secondary);
  /* Override: Hover-Farbe bleibt text-primary (kein bg-Swap) */
  --v4-state-rest-bg: var(--surface-elevated, #fff);
  --v4-state-hover-bg: var(--surface-elevated, #fff);
}
/* Hover-Farb-Override via scoped selector */
.llm-preset:hover:not(.llm-preset--active) { color: var(--text-secondary); }
.llm-preset--active {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-subtle, #f0f5ff);
}

.llm-fields { display: flex; flex-direction: column; gap: 16px; }

.llm-field { display: flex; flex-direction: column; gap: 6px; }

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
  color: var(--text-secondary);
}
.llm-input--mono { font-family: var(--font-mono); }
.llm-input:hover { border-color: var(--hairline-strong); }
.llm-input:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--focus-ring);
}

.llm-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
}
.llm-saved { font-size: 13px; color: var(--status-green, #27ae60); }
.llm-error { font-size: 13px; color: var(--status-red, #c0392b); }
</style>
