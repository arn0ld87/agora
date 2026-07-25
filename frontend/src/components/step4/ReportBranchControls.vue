<script setup lang="ts">
/**
 * ReportBranchControls — Modellauswahl für Branch-Overrides (Issue #834).
 *
 * backend/app/services/branching_service.py erlaubt `llm_profile_id` nicht
 * als Branch-Override (nur llm_model, language, max_agents, time_config,
 * enable_twitter, enable_reddit, persona_additions, persona_removals) — der
 * frühere v3-Profil-Legacy-Picker war hier funktionslos. Migriert auf den
 * kanonischen AiModelPicker.
 *
 * Genau EINE Senke im Payload (branchForm.llm_model als String), aber ZWEI
 * Schreibpfade in der UI, die beide auf dasselbe Feld zielen:
 *   1. `watch(modelRef, …)` schreibt bei jeder Picker-Auswahl.
 *   2. Das Freitext-Input ist per `v-model="branchForm.llm_model"` direkt
 *      an dasselbe Feld gebunden.
 * Es gewinnt jeweils die zuletzt ausgeführte Bearbeitung, unkommentiert für
 * die Nutzerin: ein Picker-Pick überschreibt zuvor getippten Freitext
 * kommentarlos, und umgekehrt aktualisiert Freitext-Eingabe NICHT die
 * Picker-Anzeige (`modelRef` bleibt auf der alten Auswahl stehen) — Picker
 * und Freitext-Feld können danach auseinanderlaufen. Das ist bestehendes,
 * jetzt getestetes Verhalten (siehe ReportBranchControls.spec.ts), keine
 * UX-Empfehlung.
 *
 * Ausserdem verwirft die Auswahl `provider_connection_id` — es wird nur
 * `model_id` als String gesendet, weil `allowed_override_keys` im
 * Branch-Override backend-seitig keine Connection-Referenz kennt, nur den
 * `llm_model`-String. Der Picker suggeriert optisch eine connection-
 * gebundene Route, die im Branch-Override nicht ankommt — diese Lücke
 * trägt Issue #886.
 */
import { ref, watch } from 'vue'
import Button from '@/components/v4/forms/Button.vue'
import AiModelPicker from '@/components/v4/forms/AiModelPicker.vue'
import type { AiModelRef } from '@/contracts/aiModelRef'

const emit = defineEmits<{
  create: [form: {
    branch_name: string
    llm_model: string
    language: string
    max_agents: string
  }]
}>()

defineProps<{
  branchBusy: boolean
}>()

const branchForm = ref({
  branch_name: '',
  llm_model: '',
  language: '',
  max_agents: '',
})

const modelRef = ref<AiModelRef | null>(null)
watch(modelRef, (val) => {
  branchForm.value.llm_model = val?.model_id ?? ''
})
</script>

<template>
  <div class="branch-controls">
    <input v-model="branchForm.branch_name" class="model-input" type="text" placeholder="Branch name" />
    <div class="branch-profile-cell">
      <AiModelPicker v-model="modelRef" mode="chat" />
    </div>
    <input
      v-model="branchForm.llm_model"
      class="model-input"
      type="text"
      placeholder="LLM model override"
    />
    <input v-model="branchForm.language" class="model-input" type="text" placeholder="language" />
    <input v-model="branchForm.max_agents" class="model-input" type="number" min="1" placeholder="max agents" />
    <Button
      variant="ghost"
      :loading="branchBusy"
      :disabled="branchBusy"
      @click="emit('create', { ...branchForm })"
    >
      Create Branch
    </Button>
  </div>
</template>

<style scoped>
.branch-controls {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: var(--s-3);
}
.branch-profile-cell {
  display: flex;
  align-items: center;
}
.model-input {
  background: var(--bg-elevated);
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  color: var(--fg);
  font-family: var(--ff-mono);
  font-size: var(--fs-14);
  padding: 8px 10px;
  outline: none;
}
.model-input:focus {
  border-color: var(--accent);
}
@media (max-width: 720px) {
  .branch-controls {
    grid-template-columns: 1fr;
  }
}
</style>
