<script setup lang="ts">
/**
 * RunReplayDialog — Replay-Dialog für die Run-Detail-Ansicht (Issue #763, Ticket 6;
 * Modell-Picker + 1:1-Startparameter + Deviations: Issue #1684, Teil von #1274).
 *
 * Zwei Modi:
 *   - "Identisch wiederholen": POST /replay ohne Overrides.
 *   - "Variante": POST /replay mit ReplayOverrides (Modell).
 *
 * Bewusst nur das Modell-Override: das Backend lehnt ``seed_document_id`` und
 * ``random_seed`` mit HTTP 400 ab (kein Re-Prepare-Mechanismus für ein neues
 * Ausgangsdokument, kein Runtime-Konzept für einen deterministischen Seed).
 * Eingabefelder dafür würden garantiert in einen Fehler laufen.
 *
 * Die Modellauswahl läuft ausschließlich über den kanonischen `AiModelPicker`
 * (nur vorhandene Provider-Connections/Modelle wählbar) statt über Freitext —
 * Freitext ließ jede beliebige, garantiert ungültige Route zu.
 *
 * `platform`/`max_rounds`/`enable_graph_memory_update`/`graph_id` werden vom
 * Backend 1:1 aus dem Original-Manifest übernommen und sind hier nur zur
 * Transparenz angezeigt, nicht editierbar. Fehlt `manifest.simulation`
 * (Alt-Manifest vor Issue #1274), lehnt das Backend mit
 * `409 manifest_missing_simulation_params` ab — das wird hier bereits vor dem
 * Absenden sichtbar gemacht, wenn das Original-Manifest das zeigt.
 *
 * Ist bei "Identisch wiederholen" die im Original-Manifest erfasste
 * Modell-Route nicht mehr auflösbar (Connection gelöscht/deaktiviert),
 * lehnt das Backend mit `409 manifest_route_unresolvable` ab (Issue #1686,
 * Teil von #1274) — eigene i18n-Meldung statt der rohen Backend-Zeichenkette,
 * analog zu `manifest_missing_simulation_params`.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Dialog from './v4/data/Dialog.vue'
import Button from './v4/forms/Button.vue'
import AiModelPicker from './v4/forms/AiModelPicker.vue'
import { getRunManifest, replayRun } from '../api/runs'
import { ApiError } from '../api/envelope'
import { RunManifestSchema, type ManifestDeviation } from '../contracts/runManifestContract'
import type { ManifestSimulationParams } from '../contracts/runManifestContract'
import type { AiModelRef } from '../contracts/aiModelRef'

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
type DialogPhase = 'form' | 'result'

const mode = ref<ReplayMode>('identical')
const selectedModel = ref<AiModelRef | null>(null)

const submitting = ref(false)
const errorMessage = ref('')

const phase = ref<DialogPhase>('form')
const newRunId = ref('')
const deviations = ref<ManifestDeviation[]>([])

const manifestLoading = ref(false)
const simulationParams = ref<ManifestSimulationParams | null>(null)
const manifestUnavailable = ref(false)

async function loadOriginalManifest(): Promise<void> {
  manifestLoading.value = true
  simulationParams.value = null
  manifestUnavailable.value = false
  try {
    const response = await getRunManifest(props.runId)
    const parsed = RunManifestSchema.safeParse(response.data)
    if (!parsed.success || !parsed.data.simulation) {
      manifestUnavailable.value = true
      return
    }
    simulationParams.value = parsed.data.simulation
  } catch {
    manifestUnavailable.value = true
  } finally {
    manifestLoading.value = false
  }
}

async function loadDeviations(replayedRunId: string): Promise<void> {
  try {
    const response = await getRunManifest(replayedRunId)
    const parsed = RunManifestSchema.safeParse(response.data)
    deviations.value = parsed.success ? parsed.data.deviations : []
  } catch {
    // Deviations-Anzeige ist rein informativ — ein fehlgeschlagener
    // Nachlade-Request darf den bereits erfolgreichen Replay nicht als
    // Fehler ausgeben.
    deviations.value = []
  }
}

// Formularfelder beim Öffnen zurücksetzen — kein Rest-State aus dem letzten Aufruf.
watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      mode.value = 'identical'
      selectedModel.value = null
      errorMessage.value = ''
      phase.value = 'form'
      newRunId.value = ''
      deviations.value = []
      void loadOriginalManifest()
    }
  },
  { immediate: true },
)

const canSubmit = computed(
  () =>
    !submitting.value &&
    !manifestUnavailable.value &&
    (mode.value === 'identical' || Boolean(selectedModel.value)),
)

function buildOverrides(): { ai_model_ref: { provider_connection_id: string; model_id: string } } | undefined {
  if (mode.value !== 'variant' || !selectedModel.value) return undefined
  return {
    ai_model_ref: {
      provider_connection_id: selectedModel.value.provider_connection_id,
      model_id: selectedModel.value.model_id,
    },
  }
}

async function submit(): Promise<void> {
  submitting.value = true
  errorMessage.value = ''
  try {
    const overrides = buildOverrides()
    const response = await replayRun(props.runId, overrides ? { overrides } : undefined)
    newRunId.value = response.run_id
    emit('replayed', response.run_id)
    await loadDeviations(response.run_id)
    phase.value = 'result'
  } catch (e) {
    if (e instanceof ApiError && e.code === 'manifest_missing_simulation_params') {
      errorMessage.value = t('runs.dashboard.replay.missing_simulation_params_error')
    } else if (e instanceof ApiError && e.code === 'manifest_route_unresolvable') {
      // Issue #1686 (P1): ohne Override ist die im Original-Manifest erfasste
      // Modell-Route nicht mehr auflösbar (z.B. Connection gelöscht) — das
      // Backend lehnt mit 409 ab statt still auf Workspace-Defaults
      // zurückzufallen. Eine eigene i18n-Meldung statt der rohen
      // Backend-Zeichenkette, analog zu manifest_missing_simulation_params.
      errorMessage.value = t('runs.dashboard.replay.route_unresolvable_error')
    } else {
      errorMessage.value =
        e instanceof ApiError || e instanceof Error
          ? e.message
          : t('runs.dashboard.replay.unknown_error')
    }
  } finally {
    submitting.value = false
  }
}

function formatDeviationValue(value: unknown): string {
  if (value === null || value === undefined) return t('runs.dashboard.replay.value_none')
  if (typeof value === 'boolean') return value ? t('runs.dashboard.replay.value_true') : t('runs.dashboard.replay.value_false')
  return String(value)
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
    <div v-if="phase === 'form'" class="replay-body">
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

      <p v-if="manifestUnavailable" class="manifest-warning" role="alert" data-testid="manifest-unavailable">
        {{ t('runs.dashboard.replay.no_manifest') }}
      </p>

      <div v-else-if="simulationParams" class="original-params" data-testid="original-params">
        <h3 class="section-heading">{{ t('runs.dashboard.replay.original_params_heading') }}</h3>
        <dl>
          <dt>{{ t('runs.dashboard.replay.original_params_platform') }}</dt>
          <dd>{{ simulationParams.platform }}</dd>
          <dt>{{ t('runs.dashboard.replay.original_params_max_rounds') }}</dt>
          <dd>{{ simulationParams.max_rounds ?? t('runs.dashboard.replay.value_none') }}</dd>
          <dt>{{ t('runs.dashboard.replay.original_params_graph_memory') }}</dt>
          <dd>
            {{
              simulationParams.enable_graph_memory_update
                ? t('runs.dashboard.replay.value_true')
                : t('runs.dashboard.replay.value_false')
            }}
          </dd>
          <template v-if="simulationParams.enable_graph_memory_update">
            <dt>{{ t('runs.dashboard.replay.original_params_graph_id') }}</dt>
            <dd>{{ simulationParams.memory_update_graph_id ?? t('runs.dashboard.replay.value_none') }}</dd>
          </template>
        </dl>
      </div>

      <div v-if="mode === 'variant'" class="variant-fields">
        <div class="field">
          <span class="field-label">{{ t('runs.dashboard.replay.field_model') }}</span>
          <AiModelPicker
            v-model="selectedModel"
            mode="chat"
            :placeholder="t('runs.dashboard.replay.field_model_placeholder')"
          />
        </div>
      </div>

      <p v-if="errorMessage" class="replay-error" role="alert">
        {{ t('runs.dashboard.replay.error', { message: errorMessage }) }}
      </p>
    </div>

    <div v-else class="replay-result" data-testid="replay-result">
      <p class="result-heading" role="status">
        {{ t('runs.dashboard.replay.success', { run_id: newRunId }) }}
      </p>

      <div class="deviations" data-testid="deviations-list">
        <h3 class="section-heading">{{ t('runs.dashboard.replay.deviations_heading') }}</h3>
        <p v-if="deviations.length === 0" class="deviations-none">
          {{ t('runs.dashboard.replay.deviations_none') }}
        </p>
        <ul v-else class="deviations-items">
          <li v-for="deviation in deviations" :key="deviation.field">
            <strong>{{ deviation.field }}</strong>:
            {{ formatDeviationValue(deviation.original) }} →
            {{ formatDeviationValue(deviation.replay) }}
          </li>
        </ul>
      </div>
    </div>

    <template #footer>
      <template v-if="phase === 'form'">
        <Button variant="ghost" :disabled="submitting" @click="close">
          {{ t('runs.dashboard.replay.cancel') }}
        </Button>
        <Button variant="primary" :loading="submitting" :disabled="!canSubmit" @click="submit">
          {{ submitting ? t('runs.dashboard.replay.submitting') : t('runs.dashboard.replay.submit') }}
        </Button>
      </template>
      <template v-else>
        <Button variant="primary" @click="close">
          {{ t('runs.dashboard.replay.close') }}
        </Button>
      </template>
    </template>
  </Dialog>
</template>

<style scoped>
.replay-body,
.replay-result {
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

.section-heading {
  margin: 0 0 6px;
  font-family: var(--ff-mono, monospace);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-secondary);
}

.original-params dl {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 4px 12px;
  margin: 0;
  font-size: 13px;
}

.original-params dt {
  color: var(--text-secondary);
}

.original-params dd {
  margin: 0;
}

.manifest-warning {
  margin: 0;
  padding: 8px 12px;
  background: var(--status-orange-bg, var(--status-red-bg));
  border: 1px solid var(--status-orange, var(--status-red));
  color: var(--status-orange, var(--status-red));
  font-size: 13px;
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
  color: var(--text-secondary);
}

.replay-error {
  margin: 0;
  padding: 8px 12px;
  background: var(--status-red-bg);
  border: 1px solid var(--status-red);
  color: var(--status-red);
  font-size: 13px;
}

.result-heading {
  margin: 0;
  font-size: 13px;
  color: var(--text-primary);
}

.deviations-none {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.deviations-items {
  margin: 0;
  padding-inline-start: 18px;
  font-size: 13px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
