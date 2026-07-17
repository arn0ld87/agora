<script setup lang="ts">
/**
 * Reusable Sektions-Panel fuer .env-Settings (Slice G1).
 *
 * Extrahiert aus dem klassischen SettingsView die Render-Logik fuer
 * eine gefilterte Untermenge von Sektionen (per `allowedSections`-Prop).
 * Wird von SettingsGeneralView + SettingsIntegrationsView verwendet,
 * teilt sich aber den gemeinsamen `settingsStore`-Zustand.
 *
 * Secret-Bestaetigungs-Modal bleibt drinnen — wer auf "Speichern"
 * klickt und dirty Secrets hat, sieht die Sicherheitsabfrage.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import Badge from '@/components/ui/Badge.vue'
import Button from './Button.vue'
import { useSettingsStore } from '@/store/settings'
import type { SettingsFieldMeta } from '@/contracts/settingsContract'

const props = defineProps<{
  /** Erlaubte Sektions-IDs; alle anderen werden ausgeblendet. */
  allowedSections: readonly string[]
}>()

const { t } = useI18n()
const settingsStore = useSettingsStore()
const { sections, fields, dirtySectionFlags } = storeToRefs(settingsStore)

const showSecretsModal = ref(false)
const flashMessage = ref('')

// Sektions-Reihenfolge aus dem Store, aber nur die erlaubten.
const visibleSections = computed(() =>
  sections.value.filter((s: string) => props.allowedSections.includes(s)),
)

const activeSection = ref<string>('')

// Erstmal auf die erste erlaubte Sektion springen, sobald geladen.
watch(
  visibleSections,
  (sec) => {
    if (!sec.length) {
      activeSection.value = ''
      return
    }
    if (!sec.includes(activeSection.value)) {
      activeSection.value = sec[0]
    }
  },
  { immediate: true },
)

// Felder der aktiven Sektion — typed, kein `as` mehr im Template noetig.
const currentFields = computed<SettingsFieldMeta[]>(
  () => fields.value[activeSection.value] ?? [],
)

const dirtySections = computed(() => dirtySectionFlags.value)

// Dirty-Counter: direkt ueber die vorgrupperten fields[section] iterieren.
// Spart die O(N*M) Schema-Suche aus der ersten Slice-G1-Implementierung
// (Gemini Followup zu #422).
const totalDirty = computed(() =>
  props.allowedSections.reduce((acc, section) => {
    const sectionFields = fields.value[section] ?? []
    return acc + sectionFields.filter((f) => settingsStore.isDirty(f.key)).length
  }, 0),
)

// Secret-Check ist auf die in dieser View sichtbaren Sektionen begrenzt.
// Sonst wuerde das Bestaetigungs-Modal auch bei dirty Secrets in einer
// nicht sichtbaren Sektion erscheinen (Gemini HIGH-Finding auf #422).
const hasDirtySecrets = computed(() =>
  props.allowedSections.some((section) =>
    (fields.value[section] ?? []).some((f) => f.secret && settingsStore.isDirty(f.key)),
  ),
)

onMounted(async () => {
  try {
    await settingsStore.ensureLoaded()
    await settingsStore.connectStream()
  } catch {
    /* loadError-Banner zeigt den Fehler */
  }
})

onUnmounted(() => {
  settingsStore.disconnectStream()
})

function setActive(section: string) {
  activeSection.value = section
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
    /* Inline-Errors pro Field */
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

function sectionLabel(section: string) {
  const key = `settings.sections.${section}`
  const label = t(key)
  return label === key ? section : label
}

function sourceLabel(source: string) {
  const key = `settings.source.${source}`
  const label = t(key)
  return label === key ? source : label
}

function sourceVariant(source: string) {
  if (source === 'file' || source === 'override') return 'accent'
  if (source === 'env') return 'info'
  return 'outline'
}

function setDraftValue(key: string, value: unknown) {
  ;(settingsStore.draft as Record<string, unknown>)[key] = value
}
</script>

<template>
  <div class="v4-settings-panel">
    <div v-if="settingsStore.loading" class="v4-banner">
      {{ t('settings.loading') }}
    </div>
    <div v-else-if="settingsStore.loadError" class="v4-banner v4-banner--error">
      {{ t('settings.loadFailed', { message: settingsStore.loadError }) }}
    </div>

    <div v-else-if="!visibleSections.length" class="v4-banner v4-banner--muted">
      {{ t('settings.v4.noSections') }}
    </div>

    <template v-else>
      <nav class="v4-tabs" role="tablist" :aria-label="t('settings.ariaTablist')">
        <button
          v-for="section in visibleSections"
          :key="section"
          type="button"
          role="tab"
          :aria-selected="activeSection === section"
          class="v4-tab"
          :class="{
            'v4-tab--active': activeSection === section,
            'v4-tab--dirty': dirtySections[section],
          }"
          @click="setActive(section)"
        >
          <span class="v4-tab__label">{{ sectionLabel(section) }}</span>
          <span
            v-if="dirtySections[section]"
            class="v4-tab__dot"
            :aria-label="t('settings.ariaUnsaved')"
          />
        </button>
      </nav>

      <section
        class="v4-panel"
        :aria-label="t('settings.ariaSection', { section: sectionLabel(activeSection) })"
      >
        <table class="v4-fields">
          <thead>
            <tr>
              <th class="v4-fields__col-key">{{ t('settings.table.key') }}</th>
              <th class="v4-fields__col-source">{{ t('settings.table.source') }}</th>
              <th class="v4-fields__col-input">{{ t('settings.table.value') }}</th>
              <th class="v4-fields__col-flags">{{ t('settings.table.flags') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="field in currentFields"
              :key="field.key"
              :class="{
                'v4-fields__row--dirty': settingsStore.isDirty(field.key),
                'v4-fields__row--secret': field.secret,
              }"
            >
              <th scope="row" class="v4-fields__cell-key">
                <code>{{ field.key }}</code>
              </th>
              <td class="v4-fields__cell-source">
                <Badge :variant="sourceVariant(field.source)">
                  {{ sourceLabel(field.source) }}
                </Badge>
              </td>
              <td class="v4-fields__cell-input">
                <template v-if="field.secret">
                  <input
                    type="password"
                    :aria-label="field.key"
                    class="v4-input v4-input--secret"
                    :placeholder="
                      field.is_set
                        ? t('settings.secretInput.set')
                        : t('settings.secretInput.empty')
                    "
                    :value="settingsStore.draft[field.key] || ''"
                    autocomplete="new-password"
                    @input="
                      setDraftValue(field.key, ($event.target as HTMLInputElement).value)
                    "
                  >
                </template>
                <template v-else-if="field.type === 'bool'">
                  <label class="v4-bool-row">
                    <input
                      type="checkbox"
                      :checked="settingsStore.draft[field.key] === true"
                      @change="
                        setDraftValue(field.key, ($event.target as HTMLInputElement).checked)
                      "
                    >
                    <span>{{
                      settingsStore.draft[field.key] === true
                        ? t('settings.bool.on')
                        : t('settings.bool.off')
                    }}</span>
                  </label>
                </template>
                <template v-else-if="field.type === 'enum'">
                  <select
                    :aria-label="field.key"
                    class="v4-input"
                    :value="settingsStore.draft[field.key]"
                    @change="
                      setDraftValue(field.key, ($event.target as HTMLSelectElement).value)
                    "
                  >
                    <option
                      v-for="opt in field.enum_values || []"
                      :key="opt"
                      :value="opt"
                    >
                      {{ opt }}
                    </option>
                  </select>
                </template>
                <template v-else-if="field.type === 'int' || field.type === 'float'">
                  <input
                    :aria-label="field.key"
                    class="v4-input"
                    type="number"
                    :step="field.type === 'float' ? '0.01' : '1'"
                    :value="settingsStore.draft[field.key]"
                    @input="
                      setDraftValue(field.key, ($event.target as HTMLInputElement).value)
                    "
                  >
                </template>
                <template v-else>
                  <input
                    :aria-label="field.key"
                    class="v4-input"
                    type="text"
                    :value="settingsStore.draft[field.key]"
                    @input="
                      setDraftValue(field.key, ($event.target as HTMLInputElement).value)
                    "
                  >
                </template>

                <p
                  v-for="err in settingsStore.fieldErrors(field.key)"
                  :key="err.code"
                  class="v4-hint v4-hint--error"
                >
                  {{ err.message }}
                </p>
              </td>
              <td class="v4-fields__cell-flags">
                <Badge v-if="field.secret" variant="warn">
                  {{ t('settings.flag.secret') }}
                </Badge>
                <Badge v-if="field.reload_required" variant="warn">
                  {{ t('settings.flag.reload') }}
                </Badge>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <footer class="v4-actions">
        <span v-if="flashMessage" class="v4-flash">{{ flashMessage }}</span>
        <span v-else-if="settingsStore.saveError" class="v4-flash v4-flash--error">
          {{ t('settings.saveFailed', { message: settingsStore.saveError }) }}
        </span>
        <span v-else class="v4-flash v4-flash--muted">
          {{ t('settings.dirtyCount', { count: totalDirty }, totalDirty) }}
        </span>
        <Button
          variant="ghost"
          :disabled="totalDirty === 0 || settingsStore.saving"
          @click="settingsStore.discardChanges()"
        >
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
    </template>

    <div v-if="showSecretsModal" class="v4-modal-overlay" @click.self="cancelSecretSave">
      <div class="v4-modal" role="dialog" aria-modal="true">
        <h2 class="v4-modal__title">{{ t('settings.modal.title') }}</h2>
        <i18n-t keypath="settings.modal.body" tag="p">
          <template #neoPw><code>NEO4J_PASSWORD</code></template>
          <template #authToken><code>AGORA_AUTH_TOKEN</code></template>
        </i18n-t>
        <div class="v4-modal__actions">
          <Button variant="ghost" @click="cancelSecretSave">{{ t('settings.modal.cancel') }}</Button>
          <Button variant="accent" @click="confirmSecretSave">{{ t('settings.modal.confirm') }}</Button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.v4-settings-panel {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.v4-banner {
  padding: 12px 16px;
  border-radius: 10px;
  background: var(--surface-tint);
  color: var(--text-secondary);
  font-size: 13px;
}
.v4-banner--error {
  background: var(--status-red-bg, #fee);
  color: var(--status-red, #c00);
}
.v4-banner--muted {
  background: var(--surface-inset);
  color: var(--text-tertiary);
}

.v4-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  border-bottom: 1px solid var(--hairline);
  padding-bottom: 8px;
}
.v4-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  font-family: var(--font-sans);
  font-size: 13px;
  cursor: pointer;
}
.v4-tab:hover {
  background: var(--surface-hover);
  color: var(--text-primary);
}
.v4-tab--active {
  background: var(--accent-tint-bg);
  color: var(--accent-tint-text);
  border-color: var(--accent);
}
.v4-tab--dirty {
  font-weight: 600;
}
.v4-tab__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
}

.v4-panel {
  background: var(--surface-elevated);
  border: 1px solid var(--hairline);
  border-radius: 12px;
  overflow: hidden;
}
.v4-fields {
  width: 100%;
  border-collapse: collapse;
  font-family: var(--font-sans);
  font-size: 13px;
}
.v4-fields thead th {
  text-align: left;
  padding: 12px 16px;
  background: var(--surface-tint);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-tertiary);
  font-weight: 500;
  border-bottom: 1px solid var(--hairline);
}
.v4-fields tbody td,
.v4-fields tbody th {
  padding: 12px 16px;
  border-bottom: 1px solid var(--hairline);
  vertical-align: top;
}
.v4-fields tbody tr:last-child td,
.v4-fields tbody tr:last-child th {
  border-bottom: 0;
}
.v4-fields__cell-key code {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-primary);
}
.v4-fields__row--dirty {
  background: var(--accent-tint-bg);
}
.v4-fields__col-flags {
  width: 1%;
  white-space: nowrap;
}

.v4-input {
  font-family: var(--font-sans);
  font-size: 13px;
  padding: 6px 10px;
  border: 1px solid var(--hairline-strong);
  border-radius: 8px;
  background: var(--surface-base);
  color: var(--text-primary);
  width: 100%;
  max-width: 320px;
}
.v4-input--secret {
  letter-spacing: 0.1em;
}
.v4-bool-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
}

.v4-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--status-red, #c00);
}

.v4-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: flex-end;
}
.v4-flash {
  margin-right: auto;
  font-size: 13px;
  color: var(--text-secondary);
}
.v4-flash--error {
  color: var(--status-red, #c00);
}
.v4-flash--muted {
  color: var(--text-tertiary);
}

.v4-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.v4-modal {
  background: var(--surface-elevated);
  border-radius: 14px;
  padding: 24px;
  max-width: 480px;
  width: calc(100% - 32px);
  box-shadow: var(--shadow-3);
}
.v4-modal__title {
  margin: 0 0 12px;
  font-size: 18px;
  font-weight: 600;
}
.v4-modal__actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
