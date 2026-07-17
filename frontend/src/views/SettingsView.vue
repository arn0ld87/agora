<script setup>
// Issue #133 — Settings-View: Sektions-Tabs für die .env-Sektionen,
// Field-Render-Tabelle, Save-/Reset-Buttons, Secret-Confirm-Modal.
//
// SUB4 hat alle Strings auf vue-i18n umgezogen (DE+EN, siehe
// frontend/src/i18n/locales). Reload-pflichtige Felder rendern als
// Warn-Badge mit übersetztem Text; Field-Tests in
// frontend/src/__tests__/SettingsView.spec.js.
//
// Die View ist bewusst flach: keine Sub-Components für Field-Inputs,
// solange die Logik noch klein ist. Wenn weitere Field-Typen
// dazukommen (z. B. Multi-Select für CORS-Origins), darf das
// extrahiert werden.

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AgoraGlyph from '../components/ui/AgoraGlyph.vue'
import AppFooter from '../components/AppFooter.vue'
import Badge from '../components/ui/Badge.vue'
import Button from '@/components/v4/forms/Button.vue'
import { useSettingsStore } from '../store/settings'
import {
  listLlmProviders,
  listProviderModels,
  getActiveLlmConfig,
} from '../api/llmRouting'
import { useEffectiveModelSelection } from '@/composables/useEffectiveModelSelection'

const LLM_ACTIVE_SECTION = '__llm_active__'

const { t } = useI18n()
const router = useRouter()
const settingsStore = useSettingsStore()
// Kanonischer Schreibpfad: schreibt routing/defaults.global + active-config
// im Gleichschritt (Phase-1 Konsolidierung, PHASE-1-DIVERGENZ.md).
const effectiveModel = useEffectiveModelSelection()
const { sections, schema, fields, dirtyKeys, dirtySectionFlags } = storeToRefs(settingsStore)

const activeSection = ref(LLM_ACTIVE_SECTION)

// --- LLM-Auswahl (dedicated panel) ----------------------------------------
const llmProviders = ref([])
const llmModels = ref([])
const selectedProviderId = ref('')
const selectedModel = ref('')
const llmLoadingProviders = ref(false)
const llmLoadingModels = ref(false)
const llmSaving = ref(false)
const llmError = ref('')
const llmFlash = ref('')

async function loadLlmProviders() {
  llmLoadingProviders.value = true
  llmError.value = ''
  try {
    llmProviders.value = await listLlmProviders()
  } catch (err) {
    llmError.value = (err && err.message) || t('settings.llmActive.errorLoadProviders')
  } finally {
    llmLoadingProviders.value = false
  }
}

async function loadLlmModels(providerId) {
  if (!providerId) {
    llmModels.value = []
    return
  }
  llmLoadingModels.value = true
  llmError.value = ''
  try {
    llmModels.value = await listProviderModels(providerId)
  } catch (err) {
    llmModels.value = []
    llmError.value = (err && err.message) || t('settings.llmActive.errorLoadModels')
  } finally {
    llmLoadingModels.value = false
  }
}

async function loadLlmActiveConfig() {
  try {
    const cfg = await getActiveLlmConfig()
    if (cfg && cfg.provider_id) {
      selectedProviderId.value = cfg.provider_id
      await loadLlmModels(cfg.provider_id)
    }
    if (cfg && cfg.model) {
      selectedModel.value = cfg.model
    }
  } catch (err) {
    llmError.value = (err && err.message) || t('settings.llmActive.errorLoadActive')
  }
}

async function onProviderChange(providerId) {
  selectedProviderId.value = providerId
  selectedModel.value = ''
  llmFlash.value = ''
  await loadLlmModels(providerId)
}

async function saveLlmActive() {
  if (!selectedProviderId.value || !selectedModel.value) {
    llmError.value = t('settings.llmActive.errorSelectionMissing')
    return
  }
  llmSaving.value = true
  llmError.value = ''
  llmFlash.value = ''
  try {
    // provider_id == provider_connection_id (seit 7.3.3). Über den Composable
    // wird routing/defaults.global UND active-config konsistent geschrieben.
    await effectiveModel.setGlobalSelection({
      provider_connection_id: selectedProviderId.value,
      model_id: selectedModel.value,
      source: 'explicit',
    })
    llmFlash.value = t('settings.llmActive.flashSaved')
  } catch (err) {
    llmError.value = (err && err.message) || t('settings.llmActive.errorSaveFailed')
  } finally {
    llmSaving.value = false
  }
}

const isLlmActiveTab = computed(() => activeSection.value === LLM_ACTIVE_SECTION)
const showSecretsModal = ref(false)
const flashMessage = ref('')

const currentFields = computed(
  () => fields.value?.[activeSection.value] || []
)

const dirtySections = computed(() => dirtySectionFlags.value)
const totalDirty = computed(() => dirtyKeys.value.length)

const hasDirtySecrets = computed(() => {
  return dirtyKeys.value.some((key) => {
    const spec = schema.value.find((s) => s.key === key)
    return Boolean(spec?.secret)
  })
})

onMounted(async () => {
  try {
    await settingsStore.ensureLoaded()
    await settingsStore.connectStream()
  } catch {
    // Fehler steht bereits im Store; UI zeigt loadError-Banner.
  }
  await loadLlmProviders()
  await loadLlmActiveConfig()
})

watch(activeSection, (next) => {
  if (next === LLM_ACTIVE_SECTION) {
    llmFlash.value = ''
    llmError.value = ''
  }
})

onUnmounted(() => {
  settingsStore.disconnectStream()
})

function setActive(section) {
  activeSection.value = section
}

function goHome() {
  router.push('/')
}

async function handleSave() {
  flashMessage.value = ''
  try {
    if (hasDirtySecrets.value) {
      showSecretsModal.value = true
      return
    }
    await settingsStore.saveSettings({ confirmSecrets: false })
    flashMessage.value = t('settings.saved')
  } catch {
    // Validation-Fehler werden inline pro Field gerendert.
  }
}

async function confirmSecretSave() {
  flashMessage.value = ''
  try {
    await settingsStore.saveSettings({ confirmSecrets: true })
    showSecretsModal.value = false
    flashMessage.value = t('settings.savedReloadHint')
  } catch {
    showSecretsModal.value = false
  }
}

function cancelSecretSave() {
  showSecretsModal.value = false
}

function sectionLabel(section) {
  // i18n-Keys liegen unter ``settings.sections.<id>``; der Fallback
  // auf den Sektions-Schlüssel hilft, wenn das Backend irgendwann
  // eine neue Sektion liefert, deren Übersetzung noch fehlt.
  const key = `settings.sections.${section}`
  const label = t(key)
  return label === key ? section : label
}

function sourceLabel(source) {
  const key = `settings.source.${source}`
  const label = t(key)
  return label === key ? source : label
}

function sourceVariant(source) {
  // Mapping auf existierende Badge-Variants des Design-Systems.
  if (source === 'file' || source === 'override') return 'accent'
  if (source === 'env') return 'info'
  return 'outline'
}
</script>

<template>
  <div class="page">
    <header class="brand">
      <button class="brand-link" type="button" @click="goHome">
        <AgoraGlyph class="brand-glyph" />
        <span class="brand-name">Agora</span>
      </button>
      <nav class="brand-nav">
        <button class="nav-link" type="button" @click="goHome">{{ t('settings.back') }}</button>
      </nav>
    </header>

    <main class="main">
      <section class="settings-header">
        <h1 class="title">{{ t('settings.title') }}</h1>
        <p class="subtitle">
          {{ t('settings.subtitle') }}
          <code>Defaults → .env → instance/settings.json → Override</code>.
          {{ t('settings.subtitleHint') }}
        </p>
      </section>

      <div v-if="settingsStore.loading" class="banner">
        {{ t('settings.loading') }}
      </div>
      <div v-else-if="settingsStore.loadError" class="banner banner--error">
        {{ t('settings.loadFailed', { message: settingsStore.loadError }) }}
      </div>

      <div v-if="!settingsStore.loading && sections.length" class="settings-body">
        <nav class="tabs" role="tablist" :aria-label="t('settings.ariaTablist')">
          <button
            type="button"
            role="tab"
            :aria-selected="isLlmActiveTab"
            class="tab"
            :class="{ 'tab--active': isLlmActiveTab }"
            @click="setActive(LLM_ACTIVE_SECTION)"
          >
            <span class="tab-label">{{ t('settings.llmActive.tab') }}</span>
          </button>
          <button
            v-for="section in sections"
            :key="section"
            type="button"
            role="tab"
            :aria-selected="activeSection === section"
            class="tab"
            :class="{
              'tab--active': activeSection === section,
              'tab--dirty': dirtySections[section],
            }"
            @click="setActive(section)"
          >
            <span class="tab-label">{{ sectionLabel(section) }}</span>
            <span
              v-if="dirtySections[section]"
              class="tab-dot"
              :aria-label="t('settings.ariaUnsaved')"
            />
          </button>
        </nav>

        <section
          v-if="isLlmActiveTab"
          class="panel panel--llm-active"
          :aria-label="t('settings.llmActive.ariaPanel')"
        >
          <div class="llm-active">
            <header class="llm-active__head">
              <h2 class="llm-active__title">{{ t('settings.llmActive.title') }}</h2>
              <p class="llm-active__subtitle">
                {{ t('settings.llmActive.subtitle') }}
              </p>
            </header>

            <div class="llm-active__row">
              <label class="llm-active__label" for="llm-provider-select">{{ t('settings.llmActive.providerLabel') }}</label>
              <select
                id="llm-provider-select"
                class="input"
                :value="selectedProviderId"
                :disabled="llmLoadingProviders"
                @change="onProviderChange($event.target.value)"
              >
                <option value="" disabled>
                  {{ llmLoadingProviders ? t('settings.llmActive.providerLoading') : t('settings.llmActive.providerPlaceholder') }}
                </option>
                <option
                  v-for="p in llmProviders"
                  :key="p.id"
                  :value="p.id"
                >
                  {{ p.label || p.id }}
                </option>
              </select>
            </div>

            <div class="llm-active__row">
              <label class="llm-active__label" for="llm-model-select">{{ t('settings.llmActive.modelLabel') }}</label>
              <select
                id="llm-model-select"
                class="input"
                :value="selectedModel"
                :disabled="!selectedProviderId || llmLoadingModels"
                @change="selectedModel = $event.target.value"
              >
                <option value="" disabled>
                  {{
                    !selectedProviderId
                      ? t('settings.llmActive.modelNeedsProvider')
                      : llmLoadingModels
                        ? t('settings.llmActive.modelLoading')
                        : (llmModels.length ? t('settings.llmActive.modelPlaceholder') : t('settings.llmActive.modelEmpty'))
                  }}
                </option>
                <option
                  v-for="m in llmModels"
                  :key="m.id"
                  :value="m.id"
                >
                  {{ m.id }}{{ m.label && m.label !== m.id ? ` — ${m.label}` : '' }}
                </option>
              </select>
            </div>

            <p v-if="llmFlash" class="llm-active__flash">{{ llmFlash }}</p>
            <p v-if="llmError" class="llm-active__flash llm-active__flash--error">{{ llmError }}</p>

            <div class="llm-active__actions">
              <Button
                variant="accent"
                :loading="llmSaving"
                :disabled="!selectedProviderId || !selectedModel || llmSaving"
                @click="saveLlmActive"
              >
                {{ t('settings.llmActive.save') }}
              </Button>
            </div>
          </div>
        </section>

        <section
          v-else
          class="panel"
          :aria-label="t('settings.ariaSection', { section: sectionLabel(activeSection) })"
        >
          <table class="fields">
            <thead>
              <tr>
                <th class="col-key">{{ t('settings.table.key') }}</th>
                <th class="col-source">{{ t('settings.table.source') }}</th>
                <th class="col-input">{{ t('settings.table.value') }}</th>
                <th class="col-flags">{{ t('settings.table.flags') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="field in currentFields"
                :key="field.key"
                :class="{ 'row--dirty': settingsStore.isDirty(field.key), 'row--secret': field.secret }"
              >
                <th scope="row" class="cell-key">
                  <code>{{ field.key }}</code>
                </th>
                <td class="cell-source">
                  <Badge :variant="sourceVariant(field.source)">
                    {{ sourceLabel(field.source) }}
                  </Badge>
                </td>
                <td class="cell-input">
                  <template v-if="field.secret">
                    <input
                      type="password"
                      class="input input--secret"
                      :placeholder="field.is_set ? t('settings.secretInput.set') : t('settings.secretInput.empty')"
                      :value="settingsStore.draft[field.key] || ''"
                      autocomplete="new-password"
                      @input="settingsStore.draft[field.key] = $event.target.value"
                    >
                  </template>
                  <template v-else-if="field.type === 'bool'">
                    <label class="bool-row">
                      <input
                        type="checkbox"
                        :checked="settingsStore.draft[field.key] === true"
                        @change="settingsStore.draft[field.key] = $event.target.checked"
                      >
                      <span>{{ settingsStore.draft[field.key] === true ? t('settings.bool.on') : t('settings.bool.off') }}</span>
                    </label>
                  </template>
                  <template v-else-if="field.type === 'enum'">
                    <select
                      class="input"
                      :value="settingsStore.draft[field.key]"
                      @change="settingsStore.draft[field.key] = $event.target.value"
                    >
                      <option v-for="opt in field.enum_values || []" :key="opt" :value="opt">
                        {{ opt }}
                      </option>
                    </select>
                  </template>
                  <template v-else-if="field.type === 'int' || field.type === 'float'">
                    <input
                      class="input"
                      type="number"
                      :step="field.type === 'float' ? '0.01' : '1'"
                      :value="settingsStore.draft[field.key]"
                      @input="settingsStore.draft[field.key] = $event.target.value"
                    >
                  </template>
                  <template v-else>
                    <input
                      class="input"
                      type="text"
                      :value="settingsStore.draft[field.key]"
                      @input="settingsStore.draft[field.key] = $event.target.value"
                    >
                  </template>

                  <p
                    v-for="err in settingsStore.fieldErrors(field.key)"
                    :key="err.code"
                    class="hint hint--error"
                  >{{ err.message }}</p>
                </td>
                <td class="cell-flags">
                  <Badge v-if="field.secret" variant="warn">{{ t('settings.flag.secret') }}</Badge>
                  <Badge v-if="field.reload_required" variant="warn">{{ t('settings.flag.reload') }}</Badge>
                </td>
              </tr>
            </tbody>
          </table>
        </section>

        <footer v-if="!isLlmActiveTab" class="actions">
          <span v-if="flashMessage" class="flash">{{ flashMessage }}</span>
          <span v-else-if="settingsStore.saveError" class="flash flash--error">
            {{ t('settings.saveFailed', { message: settingsStore.saveError }) }}
          </span>
          <span v-else class="flash flash--muted">
            {{ t('settings.dirtyCount', totalDirty, { count: totalDirty }) }}
          </span>
          <Button variant="ghost" :disabled="totalDirty === 0 || settingsStore.saving" @click="settingsStore.discardChanges()">
            {{ t('settings.discard') }}
          </Button>
          <Button
            variant="accent"
            :loading="settingsStore.saving"
            :disabled="totalDirty === 0 || settingsStore.saving"
            @click="handleSave"
          >
            {{ t('settings.save') }}
          </Button>
        </footer>
      </div>
    </main>

    <div v-if="showSecretsModal" class="modal-overlay" @click.self="cancelSecretSave">
      <div class="modal" role="dialog" aria-modal="true">
        <h2 class="modal-title">{{ t('settings.modal.title') }}</h2>
        <i18n-t keypath="settings.modal.body" tag="p">
          <template #neoPw><code>NEO4J_PASSWORD</code></template>
          <template #authToken><code>AGORA_AUTH_TOKEN</code></template>
        </i18n-t>
        <div class="modal-actions">
          <Button variant="ghost" @click="cancelSecretSave">{{ t('settings.modal.cancel') }}</Button>
          <Button variant="accent" @click="confirmSecretSave">{{ t('settings.modal.confirm') }}</Button>
        </div>
      </div>
    </div>

    <AppFooter />
  </div>
</template>

<style scoped>
.page {
  background: transparent;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
.brand {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--s-5) var(--s-7);
  border-bottom: 1px solid var(--rule);
}
.brand-link {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  background: transparent;
  border: 0;
  cursor: pointer;
  color: var(--fg);
}
.brand-glyph { width: 28px; height: 28px; }
.brand-name {
  font-family: var(--ff-sans);
  font-weight: 600;
  font-size: 22px;
  letter-spacing: -0.01em;
}
.nav-link {
  font-family: var(--ff-mono);
  font-size: 12px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  background: transparent;
  border: 1px solid var(--rule-strong);
  color: var(--fg);
  padding: 8px 14px;
  cursor: pointer;
  border-radius: var(--r-pill);
}
.nav-link:hover { background: var(--bg-elevated); }

.main {
  flex: 1;
  padding: var(--s-7);
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
}

.settings-header {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.title {
  font-family: var(--ff-sans);
  font-weight: 650;
  font-size: 36px;
  letter-spacing: -0.02em;
  margin: 0;
}
.subtitle {
  margin: 0;
  color: var(--fg-muted);
  font-size: var(--fs-14);
  max-width: 64ch;
}
.subtitle code {
  font-family: var(--ff-mono);
  font-size: 12px;
  background: var(--bg-elevated);
  padding: 2px 6px;
  border-radius: var(--r-2);
}

.banner {
  padding: var(--s-4);
  background: var(--bg-elevated);
  border: 1px solid var(--rule);
  border-radius: var(--r-3);
}
.banner--error {
  border-color: var(--err);
  color: var(--err);
}

.settings-body {
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
}

.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
  padding: var(--s-2);
  background: var(--bg-elevated);
  border: 1px solid var(--rule);
  border-radius: var(--r-pill);
}
.tab {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 18px;
  border-radius: var(--r-pill);
  border: 1px solid transparent;
  background: transparent;
  color: var(--fg-muted);
  font-family: var(--ff-mono);
  font-size: 12px;
  letter-spacing: var(--ls-mono-wide);
  text-transform: uppercase;
  cursor: pointer;
  transition: background 150ms ease, color 150ms ease;
}
.tab:hover { background: var(--bg-glass); color: var(--fg); }
.tab--active {
  background: var(--accent-soft);
  color: var(--fg);
  border-color: color-mix(in oklch, var(--accent) 60%, transparent);
}
.tab-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
}

.panel {
  background: var(--bg-elevated);
  border: 1px solid var(--rule);
  border-radius: var(--r-3);
  padding: var(--s-2);
  overflow-x: auto;
}

.fields {
  width: 100%;
  border-collapse: collapse;
}
.fields th, .fields td {
  padding: var(--s-3);
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--rule);
}
.fields thead th {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono-wide);
  text-transform: uppercase;
  color: var(--fg-meta);
  font-weight: 500;
}
.col-key { width: 30%; }
.col-source { width: 12%; }
.col-input { width: 38%; }
.col-flags { width: 20%; }

.cell-key code {
  font-family: var(--ff-mono);
  font-size: 13px;
  color: var(--fg);
  background: var(--bg-glass);
  padding: 2px 8px;
  border-radius: var(--r-2);
}

.cell-input .input,
.cell-input select.input {
  width: 100%;
  font-family: var(--ff-sans);
  font-size: var(--fs-14);
  height: var(--ctl-h-md);
  padding: 0 var(--ctl-pad-x);
  background: var(--bg-page);
  border: 1px solid var(--rule-strong);
  border-radius: var(--r-pill);
  color: var(--fg);
  outline: none;
  transition: border-color 150ms ease, box-shadow 150ms ease, background 150ms ease;
}
.cell-input .input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 4px var(--accent-soft);
}
.input--secret { letter-spacing: 0.2em; }

.bool-row {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  font-family: var(--ff-mono);
  font-size: 12px;
  letter-spacing: var(--ls-mono-wide);
  text-transform: uppercase;
  color: var(--fg);
}
.bool-row input { width: 18px; height: 18px; }

.cell-flags { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }

.hint {
  margin: var(--s-2) 0 0;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  color: var(--fg-meta);
}
.hint--error { color: var(--err); }

.row--dirty .cell-key code {
  background: var(--accent-soft);
}

.actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--s-3);
  padding: var(--s-4) 0;
}
.flash {
  margin-right: auto;
  font-family: var(--ff-mono);
  font-size: 12px;
  letter-spacing: var(--ls-mono);
  color: var(--fg-muted);
}
.flash--muted { color: var(--fg-meta); }
.flash--error { color: var(--err); }

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.modal {
  background: var(--bg-elevated);
  border: 1px solid var(--rule-strong);
  border-radius: var(--r-3);
  padding: var(--s-6);
  max-width: 520px;
  width: 92%;
  box-shadow: var(--shadow-2);
}
.modal-title {
  margin: 0 0 var(--s-3);
  font-family: var(--ff-sans);
  font-weight: 600;
  font-size: 24px;
  letter-spacing: -0.01em;
}
.modal p { color: var(--fg-muted); }
.modal code {
  font-family: var(--ff-mono);
  font-size: 12px;
  background: var(--bg-glass);
  padding: 2px 6px;
  border-radius: var(--r-2);
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--s-3);
  margin-top: var(--s-5);
}

.panel--llm-active {
  padding: var(--s-6);
}
.llm-active {
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
  max-width: 640px;
}
.llm-active__head { display: flex; flex-direction: column; gap: var(--s-2); }
.llm-active__title {
  margin: 0;
  font-family: var(--ff-sans);
  font-weight: 600;
  font-size: 22px;
  letter-spacing: -0.01em;
}
.llm-active__subtitle {
  margin: 0;
  color: var(--fg-muted);
  font-size: var(--fs-14);
}
.llm-active__row {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.llm-active__label {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono-wide);
  text-transform: uppercase;
  color: var(--fg-meta);
}
.llm-active .input {
  width: 100%;
  font-family: var(--ff-sans);
  font-size: var(--fs-14);
  height: var(--ctl-h-md);
  padding: 0 var(--ctl-pad-x);
  background: var(--bg-page);
  border: 1px solid var(--rule-strong);
  border-radius: var(--r-pill);
  color: var(--fg);
  outline: none;
  transition: border-color 150ms ease, box-shadow 150ms ease, background 150ms ease;
}
.llm-active .input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 4px var(--accent-soft);
}
.llm-active .input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.llm-active__flash {
  margin: 0;
  font-family: var(--ff-mono);
  font-size: 12px;
  letter-spacing: var(--ls-mono);
  color: var(--fg-muted);
}
.llm-active__flash--error { color: var(--err); }
.llm-active__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--s-3);
}
</style>
