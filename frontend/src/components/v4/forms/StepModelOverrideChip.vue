<script setup lang="ts">
/**
 * StepModelOverrideChip — Per-Step-Modellauswahl-Chip.
 *
 * Slice 5.4: Migration auf AiModelPicker (SSoT). Der AiModelPicker emittiert
 * `update:modelValue` mit einer AiModelRef, die via useAiModelRefAdapter
 * in eine LlmRoute konvertiert wird, damit der bestehende v3-Store
 * (useLlmRoutingDefaultsStore) ohne Touch weiter funktioniert.
 *
 * Zeigt das aktuell effektive Modell (Workspace-Default oder Stage-Override)
 * fuer genau eine Stage und ermoeglicht per Popover den Wechsel. Der Wechsel
 * patcht den Workspace-Default. Der Backend-Seed-Hook mergt das beim
 * Run-Start in die ``RuntimeLlmRouting``.
 *
 * Wenn ``locked`` gesetzt ist, wird der Chip read-only dargestellt (Run
 * laeuft bereits und die Stage ist versiegelt).
 *
 * Issue #1023 (Befund B-23): Ohne ``runId`` zeigte der Chip fuer einen
 * laufenden oder abgeschlossenen Run immer den Workspace-/Stage-Default
 * statt des Modells, das dieser Run fuer die Stage tatsaechlich verwendet
 * hat (`GET /api/runs/<id>/llm-routing` → `snapshots[stageId]`).
 * Modellvergleiche wurden damit dem falschen Modell zugeordnet. Mit
 * ``runId`` liest der Chip den Run-Snapshot der Stage, sobald sie
 * gestartet hat, und markiert die Quelle sichtbar (`sourceRun` /
 * `sourceDefault`). Ohne Snapshot (Stage noch nicht erreicht oder kein
 * ``runId``) bleibt der bisherige Default-Pfad aktiv.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLlmProvidersStore, useLlmRoutingDefaultsStore } from '@/store/aiModels'
import { useAiModelRefAdapter } from '@/composables/useAiModelRefAdapter'
import { getRunLlmRouting } from '@/api/llmRouting'
import AiModelPicker from './AiModelPicker.vue'
import type { StageId, ResolvedRoute } from '@/contracts/llmRoutingContract'
import type { AiModelRef } from '@/contracts/aiModelRef'

const props = withDefaults(defineProps<{
  stageId: StageId
  label?: string
  locked?: boolean
  /** Registry-Run-ID (run_...). Wenn gesetzt, hat der Run-Snapshot Vorrang. */
  runId?: string | null
}>(), {
  label: 'Modell',
  locked: false,
  runId: null,
})

const { t } = useI18n()

const providersStore = useLlmProvidersStore()
const defaultsStore = useLlmRoutingDefaultsStore()
const adapter = useAiModelRefAdapter()

const open = ref(false)
const runSnapshot = ref<ResolvedRoute | null>(null)

async function loadRunSnapshot(runId: string): Promise<void> {
  try {
    const response = await getRunLlmRouting(runId)
    runSnapshot.value = response.snapshots?.[props.stageId] ?? null
  } catch {
    // Run (noch) nicht abrufbar oder Endpoint fehlgeschlagen — Stage-Default
    // bleibt der sichtbare Fallback, kein Chip-Crash.
    runSnapshot.value = null
  }
}

watch(
  () => props.runId,
  (runId) => {
    if (runId) void loadRunSnapshot(runId)
    else runSnapshot.value = null
  },
  { immediate: true },
)

const usingRunSnapshot = computed(() => runSnapshot.value !== null)
// Ein bereits verwendeter Run-Snapshot ist nicht mehr editierbar — die Stage
// hat mit diesem Modell schon (mindestens einmal) tatsaechlich aufgerufen.
const effectiveLocked = computed(() => props.locked || usingRunSnapshot.value)

const effectiveRoute = computed(() => defaultsStore.effectiveRouteForStage(props.stageId))
const hasOverride = computed(() => props.stageId in defaultsStore.stageOverrides)

const displayLabel = computed(() => {
  if (runSnapshot.value) return `${runSnapshot.value.provider_id} · ${runSnapshot.value.model}`
  const route = effectiveRoute.value
  if (!route?.model) return t('stepModelOverrideChip.modelPlaceholder', 'Modell wählen …')
  return `${route.provider_id ?? '?'} · ${route.model}`
})

const sourceBadgeLabel = computed(() => usingRunSnapshot.value
  ? t('stepModelOverrideChip.sourceRun', 'aus Lauf')
  : t('stepModelOverrideChip.sourceDefault', 'Standard'))

// Slice 5.4: AiModelRef-Aequivalent der effektiven LlmRoute.
// Wir konvertieren via Adapter, damit der Picker den korrekten Wert
// anzeigt und der Picker bei Auswahl zurueck in eine LlmRoute
// konvertiert werden kann (bidirektionaler Glue).
const pickerModelValue = computed<AiModelRef | null>(() => {
  if (!effectiveRoute.value?.model) return null
  return adapter.toAiModelRef(effectiveRoute.value)
})

async function ensureLoaded(): Promise<void> {
  if (providersStore.providers.length === 0) {
    await providersStore.loadProviders()
  }
  if (!defaultsStore.hasLoadedOnce) {
    try {
      await defaultsStore.load()
    } catch {
      /* defaults bleiben leer — Chip zeigt "Modell waehlen …" */
    }
  }
}

onMounted(() => {
  void ensureLoaded()
})

function toggle(): void {
  if (effectiveLocked.value) return
  open.value = !open.value
}

async function selectRoute(aiRef: AiModelRef | null): Promise<void> {
  if (aiRef === null) {
    await defaultsStore.clearStageOverride(props.stageId)
  } else {
    const llmRoute = adapter.toLlmRoute(aiRef)
    await defaultsStore.setStageOverride(props.stageId, llmRoute)
  }
  open.value = false
}
</script>

<template>
  <div class="step-model-chip-wrap">
    <button
      type="button"
      class="step-model-chip"
      :class="{ 'step-model-chip--override': hasOverride, 'step-model-chip--locked': effectiveLocked }"
      :aria-expanded="open"
      :disabled="effectiveLocked"
      @click="toggle"
    >
      <span class="step-model-chip__label">{{ label }}:</span>
      <span class="step-model-chip__value">{{ displayLabel }}</span>
      <span class="step-model-chip__source" data-testid="step-model-chip-source">{{ sourceBadgeLabel }}</span>
      <span v-if="hasOverride && !usingRunSnapshot && !locked" class="step-model-chip__badge">{{ t('stepModelOverrideChip.overrideBadge', 'override') }}</span>
      <span v-if="effectiveLocked" class="step-model-chip__lock" aria-hidden="true">🔒</span>
    </button>

    <div v-if="open && !effectiveLocked" class="step-model-chip__popover">
      <AiModelPicker
        :model-value="pickerModelValue"
        :placeholder="t('stepModelOverrideChip.modelPlaceholder', 'Modell wählen …')"
        @update:model-value="selectRoute"
      />
      <div class="step-model-chip__actions">
        <button
          v-if="hasOverride"
          type="button"
          class="step-model-chip__clear"
          @click="selectRoute(null)"
        >
          {{ t('stepModelOverrideChip.clearOverride', 'Override entfernen → Default nutzen') }}
        </button>
        <button type="button" class="step-model-chip__close" @click="open = false">
          {{ t('stepModelOverrideChip.close', 'Schließen') }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.step-model-chip-wrap {
  position: relative;
  display: inline-block;
}
.step-model-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--hairline);
  background: var(--surface-elevated, #fff);
  font-size: 12px;
  cursor: pointer;
  font-family: var(--font-sans);
}
.step-model-chip:hover:not(:disabled) {
  border-color: var(--accent, #0a84ff);
}
.step-model-chip--override {
  border-color: var(--accent, #0a84ff);
  background: rgba(10, 132, 255, 0.06);
}
.step-model-chip--locked {
  opacity: 0.7;
  cursor: not-allowed;
}
.step-model-chip__label {
  color: var(--text-tertiary);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.step-model-chip__value {
  font-family: var(--font-mono, monospace);
  color: var(--text-primary);
}
.step-model-chip__source {
  font-size: 10px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.step-model-chip__badge {
  font-size: 10px;
  color: var(--accent, #0a84ff);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.step-model-chip__popover {
  position: absolute;
  z-index: 10;
  top: calc(100% + 4px);
  right: 0;
  min-width: 280px;
  padding: 12px;
  background: var(--surface-elevated, #fff);
  border: 1px solid var(--hairline);
  border-radius: var(--r-4, 8px);
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.12);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.step-model-chip__actions {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
}
.step-model-chip__clear,
.step-model-chip__close {
  background: transparent;
  border: 0;
  color: var(--text-secondary);
  cursor: pointer;
  text-decoration: underline;
}
.step-model-chip__clear:hover,
.step-model-chip__close:hover {
  color: var(--text-primary);
}
</style>
