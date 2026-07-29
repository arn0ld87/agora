<script setup lang="ts">
/**
 * RunBudgetForm — Budget-Eingaben für einen Simulations-Run (Issue #764).
 *
 * Vier optionale Limits (Tokens, Kosten, Zeit, LLM-Aufrufe) plus Durchsetzung
 * (weich/hart). v-model: RunBudgetConfig | null — null bedeutet "kein Budget"
 * (alle Felder leer). Darstellungs-Umrechnungen (USD → Micros, Minuten →
 * Sekunden) passieren hier am Rand; Preisberechnung findet nicht statt.
 *
 * Ungültige Eingaben werden am Feld markiert (aria-invalid + Fehlertext) und
 * erzeugen KEIN neues Emit — der zuletzt gültige Wert bleibt beim Parent,
 * bis die Eingabe wieder valide ist.
 */
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Field from '../forms/Field.vue'
import Input from '../forms/Input.vue'
import SegmentedControl from '../forms/SegmentedControl.vue'
import type {
  BudgetEnforcement,
  RunBudgetConfig,
} from '../../../contracts/runBudgetContract'

const props = withDefaults(
  defineProps<{
    modelValue: RunBudgetConfig | null
    disabled?: boolean
  }>(),
  {
    disabled: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: RunBudgetConfig | null]
}>()

const { t } = useI18n()

const MICROS_PER_USD = 1_000_000
const SECONDS_PER_MINUTE = 60

// --- Feldzustand (rohe Eingabestrings; Parse erst bei Änderung) ---
const tokensRaw = ref('')
const costRaw = ref('')
const durationRaw = ref('')
const callsRaw = ref('')
const enforcement = ref<BudgetEnforcement>('soft')

const errors = reactive({
  tokens: false,
  cost: false,
  duration: false,
  calls: false,
})

/** Loop-Schutz: letztes von uns emittiertes (oder gespiegeltes) Modell. */
let lastSynced = 'null'

type Parsed =
  | { kind: 'empty' }
  | { kind: 'invalid' }
  | { kind: 'value'; value: number }

/** Positive Ganzzahl; leer → nicht gesetzt; alles andere → invalid. */
function parsePositiveInt(raw: string): Parsed {
  const text = raw.trim()
  if (!text) return { kind: 'empty' }
  if (!/^\d+$/.test(text)) return { kind: 'invalid' }
  const value = Number(text)
  return Number.isSafeInteger(value) && value >= 1
    ? { kind: 'value', value }
    : { kind: 'invalid' }
}

/** USD-Betrag mit Punkt oder Komma, max. 2 Dezimalstellen → Micros. */
function parseCostToMicros(raw: string): Parsed {
  const text = raw.trim()
  if (!text) return { kind: 'empty' }
  if (!/^\d+([.,]\d{1,2})?$/.test(text)) return { kind: 'invalid' }
  const value = Math.round(Number(text.replace(',', '.')) * MICROS_PER_USD)
  return Number.isSafeInteger(value) && value >= 1
    ? { kind: 'value', value }
    : { kind: 'invalid' }
}

/** Micros → Eingabestring in de-DE-Schreibweise ("1,50"). */
function microsToCostInput(micros: number): string {
  return (micros / MICROS_PER_USD).toFixed(2).replace('.', ',')
}

function syncFromModel(value: RunBudgetConfig | null): void {
  tokensRaw.value = value?.max_tokens ? String(value.max_tokens) : ''
  costRaw.value = value?.max_cost_micros
    ? microsToCostInput(value.max_cost_micros)
    : ''
  durationRaw.value = value?.max_duration_seconds
    ? String(Math.round(value.max_duration_seconds / SECONDS_PER_MINUTE))
    : ''
  callsRaw.value = value?.max_llm_calls ? String(value.max_llm_calls) : ''
  enforcement.value = value?.enforcement ?? 'soft'
  errors.tokens = false
  errors.cost = false
  errors.duration = false
  errors.calls = false
  lastSynced = JSON.stringify(value ?? null)
}

// Externe Modell-Änderungen (z. B. Reset durch den Parent) spiegeln.
watch(
  () => props.modelValue,
  (value) => {
    if (JSON.stringify(value ?? null) === lastSynced) return
    syncFromModel(value ?? null)
  },
  { immediate: true },
)

function recompute(): void {
  const tokens = parsePositiveInt(tokensRaw.value)
  const cost = parseCostToMicros(costRaw.value)
  const duration = parsePositiveInt(durationRaw.value)
  const calls = parsePositiveInt(callsRaw.value)

  errors.tokens = tokens.kind === 'invalid'
  errors.cost = cost.kind === 'invalid'
  errors.duration = duration.kind === 'invalid'
  errors.calls = calls.kind === 'invalid'

  // Ungültige Eingabe: Feld markieren, aber kein neues Modell emittieren —
  // sonst würde ein Tippfehler still das Budget verändern oder verwerfen.
  if (errors.tokens || errors.cost || errors.duration || errors.calls) return

  const config: RunBudgetConfig = {
    schema_version: 1,
    enforcement: enforcement.value,
    currency: 'USD',
  }
  if (tokens.kind === 'value') config.max_tokens = tokens.value
  if (cost.kind === 'value') config.max_cost_micros = cost.value
  if (duration.kind === 'value') {
    config.max_duration_seconds = duration.value * SECONDS_PER_MINUTE
  }
  if (calls.kind === 'value') config.max_llm_calls = calls.value

  const hasAnyLimit =
    tokens.kind === 'value' ||
    cost.kind === 'value' ||
    duration.kind === 'value' ||
    calls.kind === 'value'
  const next = hasAnyLimit ? config : null
  lastSynced = JSON.stringify(next)
  emit('update:modelValue', next)
}

function onEnforcementChange(value: string): void {
  if (value !== 'soft' && value !== 'hard') return
  enforcement.value = value
  recompute()
}

const enforcementOptions = computed(() => [
  { value: 'soft', label: t('runBudget.enforcementSoft') },
  { value: 'hard', label: t('runBudget.enforcementHard') },
])

const enforcementHint = computed(() =>
  enforcement.value === 'hard'
    ? t('runBudget.enforcementHardHint')
    : t('runBudget.enforcementSoftHint'),
)
</script>

<template>
  <div class="rb-form" :class="{ 'rb-form--disabled': disabled }">
    <div class="rb-form__grid">
      <div class="rb-form__field">
        <Field :label="t('runBudget.maxTokensLabel')">
          <Input
            :model-value="tokensRaw"
            type="text"
            inputmode="numeric"
            :placeholder="t('runBudget.placeholderTokens')"
            :disabled="disabled"
            :aria-invalid="errors.tokens || undefined"
            :aria-describedby="errors.tokens ? 'rb-tokens-error' : undefined"
            @update:model-value="tokensRaw = $event; recompute()"
          />
        </Field>
        <p v-if="errors.tokens" id="rb-tokens-error" class="rb-form__error" role="alert">
          {{ t('runBudget.invalidPositiveInt') }}
        </p>
      </div>

      <div class="rb-form__field">
        <Field :label="t('runBudget.maxCostLabel')">
          <Input
            :model-value="costRaw"
            type="text"
            inputmode="decimal"
            :placeholder="t('runBudget.placeholderCost')"
            :disabled="disabled"
            :aria-invalid="errors.cost || undefined"
            :aria-describedby="errors.cost ? 'rb-cost-error' : undefined"
            @update:model-value="costRaw = $event; recompute()"
          />
        </Field>
        <p v-if="errors.cost" id="rb-cost-error" class="rb-form__error" role="alert">
          {{ t('runBudget.invalidCost') }}
        </p>
      </div>

      <div class="rb-form__field">
        <Field :label="t('runBudget.maxDurationLabel')">
          <Input
            :model-value="durationRaw"
            type="text"
            inputmode="numeric"
            :placeholder="t('runBudget.placeholderDuration')"
            :disabled="disabled"
            :aria-invalid="errors.duration || undefined"
            :aria-describedby="errors.duration ? 'rb-duration-error' : undefined"
            @update:model-value="durationRaw = $event; recompute()"
          />
        </Field>
        <p v-if="errors.duration" id="rb-duration-error" class="rb-form__error" role="alert">
          {{ t('runBudget.invalidPositiveInt') }}
        </p>
      </div>

      <div class="rb-form__field">
        <Field :label="t('runBudget.maxCallsLabel')">
          <Input
            :model-value="callsRaw"
            type="text"
            inputmode="numeric"
            :placeholder="t('runBudget.placeholderCalls')"
            :disabled="disabled"
            :aria-invalid="errors.calls || undefined"
            :aria-describedby="errors.calls ? 'rb-calls-error' : undefined"
            @update:model-value="callsRaw = $event; recompute()"
          />
        </Field>
        <p v-if="errors.calls" id="rb-calls-error" class="rb-form__error" role="alert">
          {{ t('runBudget.invalidPositiveInt') }}
        </p>
      </div>
    </div>

    <div class="rb-form__enforcement">
      <Field :label="t('runBudget.enforcementLabel')">
        <SegmentedControl
          :model-value="enforcement"
          :options="enforcementOptions"
          @update:model-value="onEnforcementChange"
        />
      </Field>
      <p class="rb-form__hint">{{ enforcementHint }}</p>
    </div>
  </div>
</template>

<style scoped>
.rb-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.rb-form__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}

.rb-form__field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rb-form__error {
  margin: 0;
  font-family: var(--font-sans);
  font-size: 11.5px;
  line-height: 1.35;
  color: var(--status-red);
}

.rb-form__enforcement {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.rb-form__hint {
  margin: 0;
  font-family: var(--font-sans);
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-tertiary);
}

/* SegmentedControl kennt kein disabled — optisch + interaktiv sperren. */
.rb-form--disabled {
  opacity: 0.6;
  pointer-events: none;
}
</style>
