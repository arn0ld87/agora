<script setup lang="ts">
/**
 * Budgets — Standardgrenzen für neue Läufe (#1799, Etappe 3).
 *
 * Liest und speichert über den bestehenden Settings-Store (Zod-validierte
 * Settings-API, Abschnitt `budget`). Die Oberfläche zeigt Kosten in USD und
 * Zeit in Minuten/Stunden; das Backend speichert Mikro-USD und Sekunden
 * (Umrechnung in budgets/budgetUnits.ts). Fehler der API (Validierung je
 * Feld, Speichern, Laden) werden sichtbar angezeigt.
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import SettingsGroup from '../SettingsGroup.vue'
import SettingsRow from '../SettingsRow.vue'
import { useSettingsStore } from '@/store/settings'
import {
  durationToSeconds,
  microsToUsd,
  parseWholeNumber,
  secondsToDuration,
  usdToMicros,
  type DurationUnit,
} from '../budgets/budgetUnits'

const KEY_TOKENS = 'AGORA_SIM_DEFAULT_MAX_TOKENS'
const KEY_COST = 'AGORA_SIM_DEFAULT_MAX_COST_MICROS'
const KEY_DURATION = 'AGORA_SIM_DEFAULT_MAX_DURATION_SECONDS'
const KEY_CALLS = 'AGORA_SIM_DEFAULT_MAX_LLM_CALLS'
const KEY_ENFORCEMENT = 'AGORA_SIM_DEFAULT_BUDGET_ENFORCEMENT'

type Enforcement = 'hard' | 'soft'

interface FormState {
  tokens: string
  cost: string
  duration: string
  durationUnit: DurationUnit
  calls: string
  enforcement: Enforcement
}

const { t } = useI18n()
const store = useSettingsStore()
const { fields, loading, loadError, saving, saveError } = storeToRefs(store)

const form = reactive<FormState>({
  tokens: '',
  cost: '',
  duration: '',
  durationUnit: 'minutes',
  calls: '',
  enforcement: 'hard',
})
let initial: FormState = { ...form }
const loaded = ref(false)
const localErrors = reactive<Record<string, string>>({})
const savedFlash = ref(false)

function numeric(key: string): number {
  const meta = (fields.value.budget ?? []).find((f) => f.key === key)
  const raw = meta?.value ?? meta?.default
  return typeof raw === 'number' && Number.isFinite(raw) ? raw : 0
}

function resetFormFromStore(): void {
  const meta = (fields.value.budget ?? []).find((f) => f.key === KEY_ENFORCEMENT)
  const raw = meta?.value ?? meta?.default
  const dur = secondsToDuration(numeric(KEY_DURATION))
  form.tokens = String(numeric(KEY_TOKENS))
  form.cost = microsToUsd(numeric(KEY_COST))
  form.duration = dur.value
  form.durationUnit = dur.unit
  form.calls = String(numeric(KEY_CALLS))
  form.enforcement = raw === 'soft' ? 'soft' : 'hard'
  initial = { ...form }
  for (const k of Object.keys(localErrors)) delete localErrors[k]
  loaded.value = (fields.value.budget ?? []).length > 0
}

const formDirty = computed(() =>
  (Object.keys(initial) as Array<keyof FormState>).some((k) => form[k] !== initial[k]),
)

watch(
  () => fields.value.budget,
  () => {
    if (!formDirty.value) resetFormFromStore()
  },
  { immediate: true },
)

onMounted(async () => {
  try {
    await store.ensureLoaded()
  } catch {
    /* loadError wird unten angezeigt */
  }
  if (!formDirty.value) resetFormFromStore()
})

function apiErrors(key: string): string[] {
  return store.fieldErrors(key).map((e) => e.message)
}

function errorsFor(key: string): string[] {
  const local = localErrors[key]
  return local ? [local, ...apiErrors(key)] : apiErrors(key)
}

async function save(): Promise<void> {
  savedFlash.value = false
  for (const k of Object.keys(localErrors)) delete localErrors[k]

  const tokens = parseWholeNumber(form.tokens)
  const calls = parseWholeNumber(form.calls)
  const micros = usdToMicros(form.cost)
  const seconds = durationToSeconds(form.duration, form.durationUnit)
  if (tokens === null) localErrors[KEY_TOKENS] = t('views.settingsWindow.budgets.invalidInteger')
  if (calls === null) localErrors[KEY_CALLS] = t('views.settingsWindow.budgets.invalidInteger')
  if (micros === null) localErrors[KEY_COST] = t('views.settingsWindow.budgets.invalidNumber')
  if (seconds === null) localErrors[KEY_DURATION] = t('views.settingsWindow.budgets.invalidNumber')
  if (Object.keys(localErrors).length > 0) return

  // Unveränderte Felder bleiben unberührt (kein Rundungs-Drift, keine Dirty-Flags).
  if (form.tokens !== initial.tokens) store.draft[KEY_TOKENS] = tokens
  if (form.calls !== initial.calls) store.draft[KEY_CALLS] = calls
  if (form.cost !== initial.cost) store.draft[KEY_COST] = micros
  if (form.duration !== initial.duration || form.durationUnit !== initial.durationUnit) {
    store.draft[KEY_DURATION] = seconds
  }
  if (form.enforcement !== initial.enforcement) store.draft[KEY_ENFORCEMENT] = form.enforcement

  try {
    await store.saveSettings()
    resetFormFromStore()
    savedFlash.value = true
  } catch {
    /* saveError und Feldfehler stehen im Store und werden angezeigt */
  }
}

function discard(): void {
  store.discardChanges()
  resetFormFromStore()
  savedFlash.value = false
}

const enforcementOptions = computed(() => [
  { value: 'hard', label: t('views.settingsWindow.budgets.enforcement.hard') },
  { value: 'soft', label: t('views.settingsWindow.budgets.enforcement.soft') },
])
</script>

<template>
  <div class="section-budgets">
    <p class="budgets-intro">{{ t('views.settingsWindow.budgets.intro') }}</p>

    <p v-if="loadError && !loaded" class="budgets-alert" role="alert">
      {{ t('views.settingsWindow.budgets.loadError') }} {{ loadError }}
    </p>
    <p v-else-if="!loaded" class="budgets-status" role="status">
      {{ t('views.settingsWindow.budgets.loading') }}
    </p>

    <form v-if="loaded" class="budgets-form" novalidate @submit.prevent="save">
      <SettingsGroup
        :title="t('views.settingsWindow.budgets.groupLimits')"
        :description="t('views.settingsWindow.budgets.noLimit')"
      >
        <SettingsRow
          for="budget-tokens"
          :label="t('views.settingsWindow.budgets.tokens.label')"
          :hint="t('views.settingsWindow.budgets.tokens.hint')"
        >
          <div class="budgets-field">
            <input
              id="budget-tokens"
              v-model="form.tokens"
              class="budgets-input"
              type="text"
              inputmode="numeric"
              autocomplete="off"
              :aria-invalid="errorsFor(KEY_TOKENS).length > 0"
              aria-describedby="budget-tokens-err"
            />
            <p id="budget-tokens-err" class="budgets-error" role="alert">{{ errorsFor(KEY_TOKENS).join(' ') }}</p>
          </div>
        </SettingsRow>

        <SettingsRow
          for="budget-cost"
          :label="t('views.settingsWindow.budgets.cost.label')"
          :hint="t('views.settingsWindow.budgets.cost.hint')"
        >
          <div class="budgets-field">
            <input
              id="budget-cost"
              v-model="form.cost"
              class="budgets-input"
              type="text"
              inputmode="decimal"
              autocomplete="off"
              :aria-invalid="errorsFor(KEY_COST).length > 0"
              aria-describedby="budget-cost-err"
            />
            <p id="budget-cost-err" class="budgets-error" role="alert">{{ errorsFor(KEY_COST).join(' ') }}</p>
          </div>
        </SettingsRow>

        <SettingsRow
          for="budget-duration"
          :label="t('views.settingsWindow.budgets.duration.label')"
          :hint="t('views.settingsWindow.budgets.duration.hint')"
        >
          <div class="budgets-field">
            <div class="budgets-duration">
              <input
                id="budget-duration"
                v-model="form.duration"
                class="budgets-input"
                type="text"
                inputmode="decimal"
                autocomplete="off"
                :aria-invalid="errorsFor(KEY_DURATION).length > 0"
                aria-describedby="budget-duration-err"
              />
              <select
                v-model="form.durationUnit"
                class="budgets-input"
                :aria-label="t('views.settingsWindow.budgets.duration.unit')"
              >
                <option value="minutes">{{ t('views.settingsWindow.budgets.duration.minutes') }}</option>
                <option value="hours">{{ t('views.settingsWindow.budgets.duration.hours') }}</option>
              </select>
            </div>
            <p id="budget-duration-err" class="budgets-error" role="alert">{{ errorsFor(KEY_DURATION).join(' ') }}</p>
          </div>
        </SettingsRow>

        <SettingsRow
          for="budget-calls"
          :label="t('views.settingsWindow.budgets.calls.label')"
          :hint="t('views.settingsWindow.budgets.calls.hint')"
        >
          <div class="budgets-field">
            <input
              id="budget-calls"
              v-model="form.calls"
              class="budgets-input"
              type="text"
              inputmode="numeric"
              autocomplete="off"
              :aria-invalid="errorsFor(KEY_CALLS).length > 0"
              aria-describedby="budget-calls-err"
            />
            <p id="budget-calls-err" class="budgets-error" role="alert">{{ errorsFor(KEY_CALLS).join(' ') }}</p>
          </div>
        </SettingsRow>
      </SettingsGroup>

      <SettingsGroup :title="t('views.settingsWindow.budgets.groupEnforcement')">
        <SettingsRow
          for="budget-enforcement"
          :label="t('views.settingsWindow.budgets.enforcement.label')"
          :hint="t('views.settingsWindow.budgets.enforcement.hint')"
        >
          <div class="budgets-field">
            <select
              id="budget-enforcement"
              v-model="form.enforcement"
              class="budgets-input"
              aria-describedby="budget-enforcement-err"
            >
              <option v-for="o in enforcementOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
            <p id="budget-enforcement-err" class="budgets-error" role="alert">{{ errorsFor(KEY_ENFORCEMENT).join(' ') }}</p>
          </div>
        </SettingsRow>
      </SettingsGroup>

      <p v-if="saveError" class="budgets-alert" role="alert">
        {{ t('views.settingsWindow.budgets.saveError', { message: saveError }) }}
      </p>
      <p v-else-if="savedFlash" class="budgets-status" role="status">
        {{ t('views.settingsWindow.budgets.saved') }}
      </p>

      <div class="budgets-actions">
        <button type="submit" class="budgets-btn budgets-btn--primary" :disabled="saving || !formDirty">
          {{ saving ? t('views.settingsWindow.budgets.saving') : t('views.settingsWindow.budgets.save') }}
        </button>
        <button type="button" class="budgets-btn" :disabled="saving || !formDirty" @click="discard">
          {{ t('views.settingsWindow.budgets.discard') }}
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.section-budgets,
.budgets-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.budgets-intro,
.budgets-status {
  margin: 0;
  padding: 0 4px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--fg2);
}

.budgets-alert {
  margin: 0;
  padding: 10px 14px;
  border: 1px solid var(--err);
  border-radius: var(--ag-r-10);
  font-size: 13px;
  color: var(--fg);
}

.budgets-field {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}

.budgets-duration {
  display: flex;
  gap: 6px;
}

.budgets-input {
  font: inherit;
  font-size: 13px;
  color: var(--fg);
  background: var(--s2);
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  padding: 5px 10px;
  min-width: 0;
  width: 150px;
  text-align: right;
}

select.budgets-input {
  width: auto;
  text-align: left;
}

.budgets-input[aria-invalid='true'] {
  border-color: var(--err);
}

.budgets-input:focus-visible,
.budgets-btn:focus-visible {
  outline: 2px solid var(--acc);
  outline-offset: 2px;
}

.budgets-error {
  margin: 0;
  font-size: 12.5px;
  color: var(--err);
}

.budgets-error:empty {
  display: none;
}

.budgets-actions {
  display: flex;
  gap: 8px;
}

.budgets-btn {
  appearance: none;
  font: inherit;
  font-size: 13px;
  color: var(--fg);
  background: var(--s2);
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  padding: 6px 14px;
  cursor: pointer;
}

.budgets-btn--primary {
  background: var(--acc);
  color: var(--on-acc);
  border-color: var(--acc);
}

.budgets-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
</style>
