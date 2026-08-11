<script setup lang="ts">
import { computed } from 'vue'
import type { VoiceRegister } from '@/contracts/postEventContract'

const props = defineProps<{
  personaId: string
  personaName: string
  voiceRegister: VoiceRegister
}>()

// Initialen aus dem Anzeigenamen, nicht aus der technischen persona_id —
// #1216 5a: die Nutzerin sieht einen Namen, keine ID-Muster.
const initials = computed(() =>
  (props.personaName || props.personaId).slice(0, 2).toUpperCase(),
)

const registerColor: Record<VoiceRegister, string> = {
  'formal-de': 'var(--accent-blue, #2563eb)',
  'neutral-de': 'var(--accent-green, #10b981)',
  'technical-de': 'var(--accent-amber, #d97706)',
  'skeptisch-de': 'var(--accent-purple, #a855f7)',
}
</script>

<template>
  <div class="pa-root" :title="`${personaName} · ${voiceRegister}`">
    <div class="pa-circle" :style="{ '--ring': registerColor[voiceRegister] }">
      {{ initials }}
    </div>
    <span class="pa-register" aria-hidden="true">{{ voiceRegister.charAt(0) }}</span>
  </div>
</template>

<style scoped>
.pa-root {
  position: relative;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
}
.pa-circle {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background: var(--surface-muted, #f3f4f6);
  border: 2px solid var(--ring);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-primary, #111827);
  user-select: none;
}
.pa-register {
  position: absolute;
  bottom: -2px;
  right: -2px;
  width: 14px;
  height: 14px;
  background: var(--ring);
  color: #fff;
  border-radius: 50%;
  font-size: 9px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  pointer-events: none;
}
</style>
