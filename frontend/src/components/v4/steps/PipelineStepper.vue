<template>
  <div class="pipeline-stepper" role="navigation" aria-label="Pipeline-Fortschritt">
    <template v-for="(step, index) in STEPS" :key="step.id">
      <!-- Verbindungslinie zwischen Schritten -->
      <div
        v-if="index > 0"
        class="pipeline-stepper__connector"
        :class="{
          'pipeline-stepper__connector--done': currentStep > index + 1,
          'pipeline-stepper__connector--active': currentStep === index + 1,
        }"
        aria-hidden="true"
      />

      <!-- Schritt-Knoten -->
      <button
        type="button"
        class="pipeline-stepper__step"
        :class="{
          'pipeline-stepper__step--done': currentStep > step.id,
          'pipeline-stepper__step--active': currentStep === step.id,
          'pipeline-stepper__step--future': currentStep < step.id,
        }"
        :aria-current="currentStep === step.id ? 'step' : undefined"
        :aria-label="`Schritt ${step.id}: ${step.label}`"
        :disabled="currentStep < step.id"
        @click="currentStep > step.id ? emit('navigate', step.id) : undefined"
      >
        <!-- Checkmark bei erledigtem Schritt -->
        <span v-if="currentStep > step.id" class="pipeline-stepper__icon" aria-hidden="true">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M2 6l3 3 5-5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </span>
        <!-- Schritt-Nummer bei nicht erledigt -->
        <span v-else class="pipeline-stepper__icon" aria-hidden="true">{{ step.id }}</span>

        <!-- Label -->
        <span class="pipeline-stepper__label">{{ step.label }}</span>
      </button>
    </template>
  </div>
</template>

<script setup lang="ts">
const STEPS = [
  { id: 1, label: 'Upload' },
  { id: 2, label: 'Personas' },
  { id: 3, label: 'Simulation' },
  { id: 4, label: 'Report' },
  { id: 5, label: 'Interaktion' },
] as const

defineProps<{
  currentStep: 1 | 2 | 3 | 4 | 5
}>()

const emit = defineEmits<{
  navigate: [step: number]
}>()
</script>

<style scoped>
.pipeline-stepper {
  display: flex;
  align-items: center;
  height: 48px;
  gap: 0;
  margin-bottom: 20px;
  overflow-x: auto;
  /* verhindert Layout-Shift bei schmalem Viewport */
  min-width: 0;
}

/* Verbindungslinie */
.pipeline-stepper__connector {
  flex: 1;
  min-width: 16px;
  max-width: 48px;
  height: 2px;
  background: var(--hairline, #e5e5ea);
  transition: background 0.2s;
}

.pipeline-stepper__connector--done {
  background: var(--accent, #0071e3);
}

.pipeline-stepper__connector--active {
  background: linear-gradient(to right, var(--accent, #0071e3) 50%, var(--hairline, #e5e5ea) 50%);
}

/* Schritt-Button */
.pipeline-stepper__step {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 10px;
  height: 36px;
  border: none;
  background: none;
  cursor: default;
  border-radius: 18px;
  transition: background 0.15s;
  white-space: nowrap;
  flex-shrink: 0;
}

.pipeline-stepper__step--done {
  cursor: pointer;
}

.pipeline-stepper__step--done:hover {
  background: var(--surface-hover, rgba(0, 0, 0, 0.04));
}

/* Schritt-Icon-Kreis */
.pipeline-stepper__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  font-size: 11px;
  font-weight: 700;
  font-family: var(--font-sans);
  flex-shrink: 0;
  transition: background 0.2s, color 0.2s, border-color 0.2s;
}

.pipeline-stepper__step--future .pipeline-stepper__icon {
  background: transparent;
  border: 1.5px solid var(--text-quaternary, #c7c7cc);
  color: var(--text-quaternary, #c7c7cc);
}

.pipeline-stepper__step--active .pipeline-stepper__icon {
  background: var(--accent, #0071e3);
  border: none;
  color: #fff;
}

.pipeline-stepper__step--done .pipeline-stepper__icon {
  background: var(--accent, #0071e3);
  border: none;
  color: #fff;
}

/* Label */
.pipeline-stepper__label {
  font-size: 13px;
  font-weight: 500;
  font-family: var(--font-sans);
  transition: color 0.15s;
}

.pipeline-stepper__step--future .pipeline-stepper__label {
  color: var(--text-tertiary, #8e8e93);
}

.pipeline-stepper__step--active .pipeline-stepper__label {
  color: var(--text-primary, #1d1d1f);
  font-weight: 600;
}

.pipeline-stepper__step--done .pipeline-stepper__label {
  color: var(--text-secondary, #3c3c43);
}
</style>
