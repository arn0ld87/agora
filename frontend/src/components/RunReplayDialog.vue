<script setup lang="ts">
/**
 * RunReplayDialog — Replay-Dialog für die Run-Detail-Ansicht (Issue #763, Ticket 6).
 *
 * Zwei Modi:
 *   - "Identisch wiederholen": POST /replay ohne Overrides.
 *   - "Variante": POST /replay mit ReplayOverrides (Modell).
 *
 * Bewusst nur das Modell-Override: das Backend lehnt ``seed_document_id`` und
 * ``random_seed`` mit HTTP 400 ab (kein Re-Prepare-Mechanismus für ein neues
 * Ausgangsdokument, kein Runtime-Konzept für einen deterministischen Seed).
 * Eingabefelder dafür würden garantiert in einen Fehler laufen.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Dialog from './v4/data/Dialog.vue'
import Button from './v4/forms/Button.vue'
import Input from './v4/forms/Input.vue'
import { replayRun } from '../api/runs'
import { ApiError } from '../api/envelope'
import type { ReplayOverrides } from '../contracts/runManifestContract'

const props = defineProps<{
  modelValue: boolean
  runId: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  replayed: [newRunId: string]
}>()

const { t } = useI18n()

type ReplayMode = 'identical' | 'variant'

const mode = ref<ReplayMode>('identical')
const providerConnectionId = ref('')
const modelId = ref('')

const submitting = ref(false)
const errorMessage = ref('')

// Formularfelder beim Öffnen zurücksetzen — kein Rest-State aus dem letzten Aufruf.
watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      mode.value = 'identical'
      providerConnectionId.value = ''
      modelId.value = ''
      errorMessage.value = ''
    }
  },
)

// Ein halb ausgefülltes Modell-Override (nur Connection oder nur Modell) ist
// kein gültiger AiModelRef und würde still verworfen — der Submit-Button
// bleibt in dem Fall gesperrt statt das Original-Modell zu verwenden.
const variantIncomplete = computed(
  () =>
    mode.value === 'variant' &&
    Boolean(providerConnectionId.value.trim()) !== Boolean(modelId.value.trim()),
)

const canSubmit = computed(() => !submitting.value && !variantIncomplete.value)

function buildOverrides(): ReplayOverrides | undefined {
  if (mode.value === 'identical') return undefined
  if (!providerConnectionId.value.trim() || !modelId.value.trim()) return undefined

  return {
    ai_model_ref: {
      provider_connection_id: providerConnectionId.value.trim(),
      model_id: modelId.value.trim(),
    },
  }
}

async function submit(): Promise<void> {
  submitting.value = true
  errorMessage.value = ''
  try {
    const overrides = buildOverrides()
    const response = await replayRun(props.runId, overrides ? { overrides } : undefined)
    emit('replayed', response.run_id)
    emit('update:modelValue', false)
  } catch (e) {
    errorMessage.value =
      e instanceof ApiError || e instanceof Error
        ? e.message
        : t('runs.dashboard.replay.unknown_error')
  } finally {
    submitting.value = false
  }
}

function close(): void {
  emit('update:modelValue', false)
}
</script>

<template>
  <Dialog
    :model-value="modelValue"
    :title="t('runs.dashboard.replay.dialog_title')"
    :description="t('runs.dashboard.replay.dialog_description')"
    size="md"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <div class="replay-body">
      <div class="mode-toggle" role="radiogroup" :aria-label="t('runs.dashboard.replay.dialog_title')">
        <label class="mode-option">
          <input v-model="mode" type="radio" value="identical" name="replay-mode" />
          {{ t('runs.dashboard.replay.mode_identical') }}
        </label>
        <label class="mode-option">
          <input v-model="mode" type="radio" value="variant" name="replay-mode" />
          {{ t('runs.dashboard.replay.mode_variant') }}
        </label>
      </div>

      <div v-if="mode === 'variant'" class="variant-fields">
        <label class="field">
          <span class="field-label">{{ t('runs.dashboard.replay.field_provider_connection_id') }}</span>
          <Input v-model="providerConnectionId" placeholder="conn_..." mono />
        </label>
        <label class="field">
          <span class="field-label">{{ t('runs.dashboard.replay.field_model_id') }}</span>
          <Input v-model="modelId" placeholder="gemini-2.5-pro" mono />
        </label>
        <p v-if="variantIncomplete" class="field-hint" role="status">
          {{ t('runs.dashboard.replay.model_override_incomplete') }}
        </p>
      </div>

      <p v-if="errorMessage" class="replay-error" role="alert">
        {{ t('runs.dashboard.replay.error', { message: errorMessage }) }}
      </p>
    </div>

    <template #footer>
      <Button variant="ghost" :disabled="submitting" @click="close">
        {{ t('runs.dashboard.replay.cancel') }}
      </Button>
      <Button variant="primary" :loading="submitting" :disabled="!canSubmit" @click="submit">
        {{ submitting ? t('runs.dashboard.replay.submitting') : t('runs.dashboard.replay.submit') }}
      </Button>
    </template>
  </Dialog>
</template>

<style scoped>
.replay-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.mode-toggle {
  display: flex;
  gap: 16px;
}

.mode-option {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  cursor: pointer;
}

.variant-fields {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-label {
  font-family: var(--ff-mono, monospace);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-secondary, #888);
}

.field-hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary, #888);
}

.replay-error {
  margin: 0;
  padding: 8px 12px;
  background: #fee2e2;
  border: 1px solid #f87171;
  color: #7f1d1d;
  font-size: 13px;
}
</style>
