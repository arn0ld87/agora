<script setup lang="ts">
import { computed, useId } from 'vue'
import { useI18n } from 'vue-i18n'

import { effectivePersonaFloor } from '@/constants/personaFloor'

const { t } = useI18n()
const sliderId = useId()
const numberId = useId()
const hintId = useId()

const props = defineProps({
  useAgentCap: { type: Boolean, required: true },
  maxAgents: { type: Number, required: true },
  isPreparing: { type: Boolean, default: false },
  belowQuotaWarning: { type: Boolean, default: false },
  quotaTotal: { type: Number, default: 0 },
})

const emit = defineEmits(['update:useAgentCap', 'update:maxAgents'])

/**
 * Wirksame Report-Schwelle des aktuell eingestellten Werts (UAT-001).
 *
 * Ohne Obergrenze gilt `MIN_PERSONA_TABLE_ROWS`; mit Obergrenze deren Wert,
 * wenn er kleiner ist — exakt die Auflösung, mit der das Backend den
 * `persona_floor` persistiert. Der Dialog darf keine andere Mindestzahl
 * nennen als die, an der der Bericht gemessen wird.
 */
const reportFloor = computed(() =>
  effectivePersonaFloor(props.useAgentCap ? props.maxAgents : null),
)
</script>

<template>
  <div class="agent-cap-control">
    <label class="agent-cap">
      <input
        type="checkbox"
        :checked="useAgentCap"
        :disabled="isPreparing"
        @change="emit('update:useAgentCap', ($event.target as HTMLInputElement).checked)"
      />
      <span>{{ t('step2.agentCap.label') }}</span>
    </label>
    <div v-if="useAgentCap" class="agent-cap-slider">
      <label :for="sliderId" class="sr-only">{{ t('step2.agentCap.sliderLabel') }}</label>
      <input
        :id="sliderId"
        type="range"
        :value="maxAgents"
        min="10"
        max="500"
        step="5"
        :disabled="isPreparing"
        :title="t('step2.agentCap.minimumHint')"
        :aria-describedby="hintId"
        @input="emit('update:maxAgents', Number(($event.target as HTMLInputElement).value))"
      />
      <label :for="numberId" class="sr-only">{{ t('step2.agentCap.numberLabel') }}</label>
      <input
        :id="numberId"
        type="number"
        :value="maxAgents"
        min="10"
        max="2000"
        :disabled="isPreparing"
        class="agent-cap-number"
        :title="t('step2.agentCap.minimumHint')"
        :aria-describedby="hintId"
        @input="emit('update:maxAgents', Number(($event.target as HTMLInputElement).value))"
      />
      <span :id="hintId" class="sr-only">{{ t('step2.agentCap.minimumHint') }}</span>
      <span class="meta">{{ t('step2.agentCap.unit') }}</span>
    </div>
    <!-- UAT-001: Der Dialog nannte als einzige Mindestzahl 10 (die Untergrenze
         des Feldes) und nie die Schwelle, an der der Bericht gemessen wird.
         Der Hinweis nennt genau den Wert, den das Backend als `persona_floor`
         persistiert: min(20, Obergrenze). -->
    <p class="hint" data-testid="agent-cap-report-floor">
      {{ t('step2.agentCap.reportFloor', { floor: reportFloor }) }}
    </p>
    <p v-if="belowQuotaWarning" class="hint hint--warn" role="alert">
      {{ t('step2.personaPool.belowQuotaWarning', { pool: maxAgents, quota: quotaTotal }) }}
    </p>
    <p class="hint" v-if="!useAgentCap">{{ t('step2.agentCap.unlimitedHint') }}</p>
  </div>
</template>

<style scoped>
.agent-cap-control {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.agent-cap {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  font-family: var(--ff-mono);
  font-size: 12px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg);
  cursor: pointer;
}
.agent-cap-slider {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  margin-top: var(--s-2);
}
.agent-cap-slider input[type=range] {
  flex: 1;
  accent-color: var(--accent);
}
.agent-cap-number {
  width: 80px;
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--rule-strong);
  font-family: var(--ff-mono);
  font-size: var(--fs-16);
  padding: 4px 0;
  color: var(--fg);
  outline: none;
  text-align: right;
}
.agent-cap-number:focus { border-bottom-color: var(--accent); }
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
.hint {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  margin: 0;
}
.hint--warn {
  color: var(--warn);
}
.meta {
  color: var(--text-secondary);
  font-family: var(--font-sans);
  letter-spacing: 0;
  text-transform: none;
}
</style>
