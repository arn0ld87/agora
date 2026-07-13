<!-- legacy-model-picker-allow: pre-5.5 v3 picker importer — see docs/epics/onboarding-provider-unification/slice-5-subplan.md (5.4 migrates, 5.5 removes) -->
<script setup lang="ts">
import { ref, watch } from 'vue'
import Button from '@/components/v4/forms/Button.vue'
import LlmProfilePicker from '@/components/llm/LlmProfilePicker.vue'

const emit = defineEmits<{
  create: [form: {
    branch_name: string
    llm_model: string
    llm_profile_id: string
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
  llm_profile_id: '',
  language: '',
  max_agents: '',
})

const profileIdModel = ref<string | null>(null)
watch(profileIdModel, (val) => {
  branchForm.value.llm_profile_id = val ?? ''
})
</script>

<template>
  <div class="branch-controls">
    <input v-model="branchForm.branch_name" class="model-input" type="text" placeholder="Branch name" />
    <div class="branch-profile-cell">
      <LlmProfilePicker v-model="profileIdModel" />
    </div>
    <input
      v-model="branchForm.llm_model"
      class="model-input"
      :class="{ 'is-overridden-by-profile': profileIdModel }"
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
.model-input.is-overridden-by-profile {
  opacity: 0.6;
}
@media (max-width: 720px) {
  .branch-controls {
    grid-template-columns: 1fr;
  }
}
</style>
