<template>
  <div v-if="maxRound > 0" class="graph-round-slider">
    <div class="slider-header">
      <span class="slider-title">Round</span>
      <span class="slider-value">
        {{ displayValue }}
        <span class="slider-total">/ {{ maxRound }}</span>
      </span>
    </div>
    <input
      class="slider-input"
      type="range"
      :min="0"
      :max="maxRound"
      :step="1"
      :value="modelValue ?? maxRound"
      @input="onInput"
    />
    <div class="slider-actions">
      <button
        class="slider-btn"
        type="button"
        :disabled="modelValue == null"
        @click="reset"
      >
        Live
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: {
    type: Number,
    default: null,
  },
  maxRound: {
    type: Number,
    required: true,
  },
})

const emit = defineEmits(['update:modelValue'])

const displayValue = computed(() => (props.modelValue ?? props.maxRound))

function onInput(event) {
  const next = Number(event.target.value)
  emit('update:modelValue', next === props.maxRound ? null : next)
}

function reset() {
  emit('update:modelValue', null)
}
</script>

<style scoped>
.graph-round-slider {
  position: absolute;
  bottom: var(--s-5);
  right: var(--s-5);
  background: var(--paper-0);
  padding: var(--s-3) var(--s-4);
  border-radius: var(--r-1);
  border: 1px solid var(--rule);
  z-index: 10;
  width: 220px;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.slider-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  font-family: var(--ff-mono);
  font-size: 11px;
}

.slider-title {
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: var(--ls-mono);
  font-weight: 500;
}

.slider-value {
  color: var(--fg-body);
  font-variant-numeric: tabular-nums;
}

.slider-total {
  color: var(--fg-muted, #888);
  margin-left: 2px;
}

.slider-input {
  width: 100%;
  accent-color: var(--accent);
  cursor: pointer;
}

.slider-actions {
  display: flex;
  justify-content: flex-end;
}

.slider-btn {
  font-family: var(--ff-mono);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: var(--ls-mono);
  background: transparent;
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  color: var(--fg-body);
  padding: 2px 8px;
  cursor: pointer;
}

.slider-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.slider-btn:not(:disabled):hover {
  background: var(--paper-1);
}
</style>
