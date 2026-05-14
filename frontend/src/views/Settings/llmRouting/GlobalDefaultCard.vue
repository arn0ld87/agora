<script setup lang="ts">
import { ref } from 'vue'
import Card from '@/components/v4/forms/Card.vue'
import Field from '@/components/v4/forms/Field.vue'
import Select from '@/components/v4/forms/Select.vue'
import { PROVIDER_OPTIONS, MODEL_OPTIONS, EFFORT_OPTIONS, INITIAL_GLOBAL_DEFAULT } from './mockData'

const provider = ref(INITIAL_GLOBAL_DEFAULT.provider)
const model    = ref(INITIAL_GLOBAL_DEFAULT.model)
const effort   = ref(INITIAL_GLOBAL_DEFAULT.effort)
</script>

<template>
  <Card title="Global Default">
    <div class="gdc-fields">
      <Field label="Provider">
        <Select v-model="provider" :options="PROVIDER_OPTIONS" />
      </Field>
      <Field label="Model">
        <Select v-model="model" :options="MODEL_OPTIONS" />
      </Field>
      <Field label="Reasoning effort">
        <Select v-model="effort" :options="EFFORT_OPTIONS" />
      </Field>
    </div>

    <div class="gdc-json">
      <div class="gdc-json__label">Provider options (JSON)</div>
      <pre class="gdc-json__pre">{{ INITIAL_GLOBAL_DEFAULT.providerOptions }}</pre>
    </div>
  </Card>
</template>

<style scoped>
.gdc-fields {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 14px;
}

.gdc-json {
  margin-top: 16px;
}

.gdc-json__label {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 6px;
  font-family: var(--font-sans);
}

.gdc-json__pre {
  margin: 0;
  padding: 12px;
  background: var(--surface-elevated, #fff);
  border: 1px solid var(--hairline);
  border-radius: 8px;
  font-family: var(--font-mono);
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre;
  overflow-x: auto;
}
</style>
