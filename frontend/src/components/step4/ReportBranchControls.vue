<script setup lang="ts">
import { ref } from 'vue'
import Button from '@/components/v4/forms/Button.vue'

const emit = defineEmits<{
  create: [form: { branch_name: string; llm_model: string; language: string; max_agents: string }]
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
</script>

<template>
  <div class="branch-controls">
    <input v-model="branchForm.branch_name" class="model-input" type="text" placeholder="Branch name" />
    <input v-model="branchForm.llm_model" class="model-input" type="text" placeholder="LLM model override" />
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
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--s-3);
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
