<script setup lang="ts">
import { ref } from 'vue'
import Card from '@/components/v4/forms/Card.vue'
import Input from '@/components/v4/forms/Input.vue'

interface CustomModelForm {
  provider: string
  modelId: string
  baseUrl: string
  capabilities: string
}

const form = ref<CustomModelForm>({
  provider:     'ollama_cloud',
  modelId:      'kimi-k2.6:cloud',
  baseUrl:      'https://api.ollama.com/v1',
  capabilities: 'chat, tools, json, reasoning',
})

function save() {
  // Backend-Verdrahtung: Slice G
}

function cancel() {
  form.value = {
    provider:     'ollama_cloud',
    modelId:      'kimi-k2.6:cloud',
    baseUrl:      'https://api.ollama.com/v1',
    capabilities: 'chat, tools, json, reasoning',
  }
}
</script>

<template>
  <Card
    title="Custom Model hinzufügen"
    subtitle="Für Modelle, die nicht automatisch in der API-Liste auftauchen."
  >
    <div class="cmc-grid">
      <span class="cmc-label">Provider</span>
      <Input v-model="form.provider" mono />

      <span class="cmc-label">Model ID</span>
      <Input v-model="form.modelId" mono />

      <span class="cmc-label">Base URL</span>
      <Input v-model="form.baseUrl" mono />

      <span class="cmc-label">Capabilities</span>
      <Input v-model="form.capabilities" />
    </div>

    <div class="cmc-actions">
      <button class="cmc-btn cmc-btn--primary" type="button" @click="save">Speichern</button>
      <button class="cmc-btn cmc-btn--secondary" type="button" @click="cancel">Abbrechen</button>
    </div>
  </Card>
</template>

<style scoped>
.cmc-grid {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 12px;
  align-items: center;
}

.cmc-label {
  font-size: 13px;
  color: var(--text-secondary);
  font-family: var(--font-sans);
  line-height: 1;
}

.cmc-actions {
  display: flex;
  gap: 8px;
  margin-top: 20px;
}

/* Inline-Buttons */
.cmc-btn {
  display: inline-flex;
  align-items: center;
  height: 34px;
  padding: 0 14px;
  border-radius: 8px;
  font-family: var(--font-sans);
  font-size: 13.5px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 120ms ease, border-color 120ms ease;
}

.cmc-btn--primary {
  background: var(--accent, #0a84ff);
  color: #fff;
  border-color: var(--accent, #0a84ff);
}

.cmc-btn--primary:hover {
  background: var(--accent-hover, #006edb);
  border-color: var(--accent-hover, #006edb);
}

.cmc-btn--secondary {
  background: var(--surface-elevated, #fff);
  color: var(--text-primary);
  border-color: var(--hairline);
}

.cmc-btn--secondary:hover {
  background: var(--surface-inset, #f2f2f7);
}
</style>
