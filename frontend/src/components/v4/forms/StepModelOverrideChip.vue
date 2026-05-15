<script setup lang="ts">
/**
 * StepModelOverrideChip — Per-Step-Modellauswahl-Chip.
 *
 * Zeigt das aktuell effektive Modell (Workspace-Default oder Stage-Override)
 * für genau eine Stage und erlaubt per Popover den Wechsel. Der Wechsel
 * patcht den Workspace-Default. Der Backend-Seed-Hook mergt das beim
 * Run-Start in die ``RuntimeLlmRouting``.
 *
 * Wenn ``locked`` gesetzt ist, wird der Chip read-only dargestellt (Run
 * läuft bereits und die Stage ist versiegelt).
 */
import { computed, onMounted, ref } from 'vue'
import { useLlmProvidersStore } from '@/store/llmProviders'
import { useLlmRoutingDefaultsStore } from '@/store/llmRoutingDefaults'
import ModelPicker from './ModelPicker.vue'
import type { StageId, StageLLMRoute } from '@/contracts/llmRoutingContract'

const props = withDefaults(defineProps<{
  stageId: StageId
  label?: string
  locked?: boolean
}>(), {
  label: 'Modell',
  locked: false,
})

const providersStore = useLlmProvidersStore()
const defaultsStore = useLlmRoutingDefaultsStore()

const open = ref(false)

const effectiveRoute = computed<StageLLMRoute>(() => defaultsStore.effectiveRouteForStage(props.stageId))
const hasOverride = computed(() => props.stageId in defaultsStore.stageOverrides)

const displayLabel = computed(() => {
  const route = effectiveRoute.value
  if (!route?.model) return 'Modell wählen …'
  return `${route.provider_id ?? '?'} · ${route.model}`
})

async function ensureLoaded(): Promise<void> {
  if (providersStore.providers.length === 0) {
    await providersStore.loadProviders()
  }
  // hasLoadedOnce ist robuster als updated_at-Proxy: updated_at ist legitimerweise
  // null bei einer frischen Workspace ohne gespeicherte Defaults (Gemini MEDIUM #5).
  if (!defaultsStore.hasLoadedOnce) {
    try {
      await defaultsStore.load()
    } catch {
      /* defaults bleiben leer — Chip zeigt "Modell wählen …" */
    }
  }
}

onMounted(() => {
  void ensureLoaded()
})

function toggle(): void {
  if (props.locked) return
  open.value = !open.value
}

async function selectRoute(route: StageLLMRoute | null): Promise<void> {
  if (route === null) {
    await defaultsStore.clearStageOverride(props.stageId)
  } else {
    await defaultsStore.setStageOverride(props.stageId, route)
  }
  open.value = false
}
</script>

<template>
  <div class="step-model-chip-wrap">
    <button
      type="button"
      class="step-model-chip"
      :class="{ 'step-model-chip--override': hasOverride, 'step-model-chip--locked': locked }"
      :aria-expanded="open"
      :disabled="locked"
      @click="toggle"
    >
      <span class="step-model-chip__label">{{ label }}:</span>
      <span class="step-model-chip__value">{{ displayLabel }}</span>
      <span v-if="hasOverride && !locked" class="step-model-chip__badge">override</span>
      <span v-if="locked" class="step-model-chip__lock" aria-hidden="true">🔒</span>
    </button>

    <div v-if="open && !locked" class="step-model-chip__popover">
      <ModelPicker
        :model-value="effectiveRoute.model ? effectiveRoute : null"
        placeholder="Modell wählen …"
        @update:model-value="selectRoute"
      />
      <div class="step-model-chip__actions">
        <button
          v-if="hasOverride"
          type="button"
          class="step-model-chip__clear"
          @click="selectRoute(null)"
        >
          Override entfernen → Default nutzen
        </button>
        <button type="button" class="step-model-chip__close" @click="open = false">
          Schließen
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
