<template>
  <!-- Building/Simulating Hint -->
  <div v-if="showBuildingHint" class="graph-building-hint">
    <div class="memory-icon-wrapper">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="memory-icon">
        <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-4.04z" />
        <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-4.04z" />
      </svg>
    </div>
    {{ buildingHintLabel }}
  </div>

  <!-- Simulation Finished Hint -->
  <div v-if="showFinishedHint" class="graph-building-hint finished-hint">
    <div class="hint-icon-wrapper">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="hint-icon">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="16" x2="12" y2="12"></line>
        <line x1="12" y1="8" x2="12.01" y2="8"></line>
      </svg>
    </div>
    <span class="hint-text">Some content is still being processed. It is recommended to manually refresh the graph later</span>
    <button class="hint-close-btn" @click="$emit('dismiss-finished')" title="Close hint">
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="18" y1="6" x2="6" y2="18"></line>
        <line x1="6" y1="6" x2="18" y2="18"></line>
      </svg>
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  currentPhase: { type: Number, default: null },
  isSimulating: { type: Boolean, default: false },
  showFinishedHint: { type: Boolean, default: false },
})

defineEmits(['dismiss-finished'])

const showBuildingHint = computed(() => props.currentPhase === 1 || props.isSimulating)
const buildingHintLabel = computed(() =>
  props.isSimulating
    ? 'GraphRAG short-term/long-term memory updating in real-time'
    : 'Updating in real-time...',
)
</script>

<style scoped>
.graph-building-hint {
  position: absolute;
  bottom: 160px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--bg-inverse);
  color: var(--bg);
  padding: 8px 16px;
  border-radius: var(--r-pill);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  display: flex;
  align-items: center;
  gap: var(--s-2);
  border: 1px solid var(--mono-200);
  z-index: 100;
}

.memory-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  animation: breathe 2s ease-in-out infinite;
}

.memory-icon {
  width: 14px;
  height: 14px;
  color: var(--accent);
}

@keyframes breathe {
  0%, 100% { opacity: 0.6; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.1); }
}

.graph-building-hint.finished-hint {
  background: var(--bg-inverse);
  border: 1px solid var(--mono-200);
}

.finished-hint .hint-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
}

.finished-hint .hint-icon {
  width: 14px;
  height: 14px;
  color: var(--bg);
}

.finished-hint .hint-text {
  flex: 1;
  white-space: nowrap;
}

.hint-close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  background: transparent;
  border: 1px solid var(--mono-200);
  border-radius: 50%;
  cursor: pointer;
  color: var(--bg);
  transition: border-color 150ms ease, color 150ms ease;
  margin-left: var(--s-2);
  flex-shrink: 0;
}

.hint-close-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
</style>
